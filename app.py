from flask import Flask, render_template, jsonify, request, send_from_directory
from database import db, init_db, LottoResult, SavedNumber
from prediction_engine import prediction_engine
import os
import data_collector
from flask_apscheduler import APScheduler
from flask_cors import CORS
import threading

app = Flask(__name__)
CORS(app) # 모든 경로에 대해 CORS 허용 (모바일 앱 연동용)

# 데이터베이스 설정
# Railway 배포 시 환경 변수 DATABASE_PATH를 /data/lotto.db 등으로 설정하여 데이터를 보존할 수 있습니다.
db_path = os.environ.get('DATABASE_PATH', os.path.join(os.path.dirname(__file__), 'lotto.db'))
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# DB 초기화
init_db(app)

# 스케줄러 설정
scheduler = APScheduler()
app.config['SCHEDULER_API_ENABLED'] = True

@scheduler.task('cron', id='update_lotto_data', day_of_week='sun', hour=0, minute=5)
def scheduled_update():
    """매주 일요일 자정 5분에 최신 데이터 업데이트"""
    print("[자동 업데이트] 최신 로또 번호를 수집합니다...")
    data_collector.update_to_latest()

scheduler.init_app(app)
scheduler.start()

# 서버 시작 시 백그라운드에서 전체 데이터 업데이트 실행
def startup_update():
    print("[시스템] 시작 시 데이터 업데이트를 확인합니다...")
    data_collector.update_to_latest()

threading.Thread(target=startup_update, daemon=True).start()

# ===== PWA 지원: Service Worker는 루트 경로에 있어야 함 =====
@app.route('/sw.js')
def service_worker():
    """Service Worker를 루트 경로에서 서빙 (PWA 필수)"""
    return send_from_directory('static', 'service-worker.js',
                               mimetype='application/javascript')

# ===== Google TWA 인증 (Digital Asset Links) =====
@app.route('/.well-known/assetlinks.json')
def asset_links():
    """구글 플레이 스토어 앱 연동 인증 파일"""
    return send_from_directory('.well-known', 'assetlinks.json',
                               mimetype='application/json')

@app.route('/privacy')
def privacy():
    """구글 플레이 스토어 필수: 개인정보 처리방침"""
    return render_template('privacy.html')

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/status')
def status():
    latest_result = LottoResult.query.order_by(LottoResult.drw_no.desc()).first()
    return jsonify({
        "status": "online",
        "latest_draw": latest_result.drw_no if latest_result else None,
        "total_data": LottoResult.query.count()
    })

@app.route('/api/generate', methods=['POST'])
def generate():
    """AI 번호 생성 API"""
    data = request.json
    include = data.get('include', [])
    exclude = data.get('exclude', [])
    
    try:
        combinations = prediction_engine.generate_numbers(include, exclude, count=5)
        return jsonify({"success": True, "combinations": combinations})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/save', methods=['POST'])
def save_number():
    """번호 저장 API"""
    data = request.json
    nums = data.get('numbers', [])
    if len(nums) != 6:
        return jsonify({"success": False, "error": "Invalid numbers"}), 400
    
    new_save = SavedNumber(
        num1=nums[0], num2=nums[1], num3=nums[2],
        num4=nums[3], num5=nums[4], num6=nums[5],
        prediction_score=data.get('score', 0)
    )
    db.session.add(new_save)
    db.session.commit()
    return jsonify({"success": True, "id": new_save.id})

@app.route('/api/saved', methods=['GET'])
def get_saved():
    """저장된 번호 목록 조회 API"""
    saved = SavedNumber.query.order_by(SavedNumber.created_at.desc()).all()
    results = []
    for s in saved:
        results.append({
            "id": s.id,
            "numbers": [s.num1, s.num2, s.num3, s.num4, s.num5, s.num6],
            "score": s.prediction_score,
            "date": s.created_at.strftime("%Y-%m-%d"),
            "is_purchased": s.is_purchased,
            "win_rank": s.win_rank
        })
    return jsonify({"success": True, "saved": results})

@app.route('/api/stats', methods=['GET'])
def get_stats():
    """통계 데이터 조회 API"""
    try:
        df = prediction_engine.get_historical_df()
        if len(df) == 0:
            # 데이터 없을 때도 빈 분석 결과 반환 (에러 대신)
            return jsonify({
                "success": True,
                "analysis": {
                    "frequency": {},
                    "hot": [],
                    "cold": [],
                    "message": "데이터 수집 중... 잠시 후 다시 시도해주세요."
                }
            })
        analysis = prediction_engine.analyze_patterns(df)
        return jsonify({"success": True, "analysis": analysis})
    except Exception as e:
        return jsonify({
            "success": True,
            "analysis": {
                "frequency": {},
                "hot": [],
                "cold": [],
                "message": f"분석 오류: {str(e)}"
            }
        })

import pandas as pd

@app.route('/api/upload_excel', methods=['POST'])
def upload_excel():
    """엑셀 파일을 통한 대량 데이터 업로드"""
    if 'file' not in request.files:
        return jsonify({"success": False, "error": "No file"}), 400
    
    file = request.files['file']
    try:
        # 동행복권 엑셀은 보통 상단 2~3행이 제목이므로 skip하게 처리
        # 버전이나 형식에 따라 다를 수 있으니 유연하게 대응
        df = pd.read_excel(file)
        
        # 실제 데이터 시작점 찾기 (회차 컬럼이 있는 행)
        start_idx = -1
        for i, row in df.iterrows():
            if '회차' in str(row.values) or 'drwNo' in str(row.values):
                start_idx = i
                break
        
        if start_idx == -1:
            # 기본 형식으로 시도
            df = pd.read_excel(file, skiprows=2)
        else:
            df = pd.read_excel(file, skiprows=start_idx + 1)
            # 컬럼명 수동 지정 (동행복권 엑셀 표준 순서)
            # 순서: 회차, 추첨일, 1등당첨자수, 1등당첨금액, ..., 1, 2, 3, 4, 5, 6, 보너스
            # 실제 엑셀을 보면 보통 뒤쪽에 번호가 있음. 컬럼명을 확인해서 매핑
            
        # 컬럼명 정규화 (필요한 컬럼만 추출)
        # 동행복권 엑셀 표준 컬럼 (뒤에서부터 번호가 오는 경우가 많음)
        # 보통 끝에서 7번째~끝이 번호임
        
        count = 0
        for _, row in df.iterrows():
            try:
                # 회차 번호 추출
                drw_no = int(row.iloc[0])
                if LottoResult.query.get(drw_no): continue # 중복 스킵
                
                # 번호 위치는 엑셀마다 다를 수 있으나 보통 연속해서 있음
                # 안전하게 '1', '2'.. 혹은 숫자가 들어있는 컬럼 탐색
                nums = []
                for val in row.values:
                    if str(val).isdigit() and 1 <= int(val) <= 45:
                        nums.append(int(val))
                
                if len(nums) < 7: continue # 번호가 부족하면 스킵
                
                # 보통 마지막이 보너스 번호
                res = LottoResult(
                    drw_no=drw_no,
                    drw_no_date=str(row.iloc[1]),
                    num1=nums[0], num2=nums[1], num3=nums[2],
                    num4=nums[3], num5=nums[4], num6=nums[5],
                    bonus_num=nums[6]
                )
                db.session.add(res)
                count += 1
            except:
                continue
        
        db.session.commit()
        return jsonify({"success": True, "count": count})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/admin/update_data', methods=['POST'])
def manual_update():
    """수동 데이터 업데이트 트리거"""
    try:
        # 백그라운드 스레드 대신 동기적으로 실행하여 결과를 알려줌
        # (시간이 걸릴 수 있으므로 모바일에서는 로딩 표시 필요)
        data_collector.update_to_latest()
        return jsonify({"success": True, "message": "업데이트 완료"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

if __name__ == '__main__':
    # host='0.0.0.0' → 같은 Wi-Fi의 모든 기기에서 접속 가능
    app.run(debug=True, host='0.0.0.0', port=5000)
