"""
data_collector.py
Flask 앱과 독립적으로 동행복권 API에서 과거 회차를 수집하여 lotto.db에 저장합니다.
"""
import requests
import sqlite3
import time
import os

# DB 파일 경로
DB_PATH = os.environ.get('DATABASE_PATH', os.path.join(os.path.dirname(__file__), 'lotto.db'))


def ensure_table(conn):
    """테이블이 없으면 생성"""
    conn.execute('''
        CREATE TABLE IF NOT EXISTS lotto_results (
            drw_no         INTEGER PRIMARY KEY,
            drw_no_date    TEXT,
            num1           INTEGER NOT NULL,
            num2           INTEGER NOT NULL,
            num3           INTEGER NOT NULL,
            num4           INTEGER NOT NULL,
            num5           INTEGER NOT NULL,
            num6           INTEGER NOT NULL,
            bonus_num      INTEGER NOT NULL,
            first_win_amnt INTEGER,
            first_przwner_co INTEGER
        )
    ''')
    conn.commit()


# 글로벌 세션 객체 (연결 재사용으로 성능 및 안정성 향상)
session = requests.Session()
session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'application/json, text/javascript, */*; q=0.01',
    'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7',
})

def get_lotto_data(drw_no):
    """특정 회차 데이터 조회 (세션 사용 및 상세 에러 로깅)"""
    url = f"https://www.dhlottery.co.kr/common.do?method=getLottoNumber&drwNo={drw_no}"
    try:
        # 타임아웃을 15초로 넉넉하게 설정
        resp = session.get(url, timeout=15)
        if resp.status_code != 200:
            print(f"  [HTTP 오류] {drw_no}회차: Status {resp.status_code}", flush=True)
            return None
        data = resp.json()
        if data.get('returnValue') == 'success':
            return data
        else:
            print(f"  [API 오류] {drw_no}회차: {data.get('returnValue')}", flush=True)
    except requests.exceptions.SSLError as e:
        print(f"  [SSL 오류] {drw_no}회차: {e}", flush=True)
    except requests.exceptions.Timeout:
        print(f"  [타임아웃] {drw_no}회차: 요청 시간이 초과되었습니다.", flush=True)
    except Exception as e:
        print(f"  [기타 오류] {drw_no}회차: {e}", flush=True)
    return None

def find_latest_draw():
    """1160회부터 순차 탐색으로 최신 회차 확인 (탐색 범위 확대)"""
    print("[탐색] 최신 회차 확인 중...")
    # 최근 회차를 기준으로 탐색 시작점 조정
    curr = 1100 
    max_fail = 3
    fail_count = 0
    
    while fail_count < max_fail:
        data = get_lotto_data(curr + 1)
        if data:
            curr += 1
            fail_count = 0 # 성공 시 초기화
        else:
            fail_count += 1
            time.sleep(1.0)
            
    print(f"[탐색 완료] 최신 회차: {curr}회")
    return curr

def collect(start_drw=1, years=None):
    """지정한 범위의 데이터를 수집합니다. (안정성 강화)"""
    conn = sqlite3.connect(DB_PATH)
    ensure_table(conn)

    latest = find_latest_draw()
    if latest < 1:
        print("[오류] 최신 회차 탐색 실패. 네트워크를 확인해주세요.")
        conn.close()
        return

    # 수집 시작점 결정
    if years:
        count_to_collect = years * 52
        start = max(1, latest - count_to_collect + 1)
    else:
        start = start_drw

    # 중복되지 않은 회차만 필터링해서 작업량 계산
    rows = conn.execute('SELECT drw_no FROM lotto_results WHERE drw_no BETWEEN ? AND ?', (start, latest)).fetchall()
    existing_nos = {r[0] for r in rows}
    
    targets = [d for d in range(latest, start - 1, -1) if d not in existing_nos]
    total_targets = len(targets)
    
    if total_targets == 0:
        print("[알림] 이미 모든 데이터가 최신 상태입니다.")
        conn.close()
        return

    print(f"[수집 시작] 신규 {total_targets}회차 수집 예정 ({start}회 ~ {latest}회)\n")

    saved = 0
    consecutive_failures = 0

    for i, drw in enumerate(targets):
        try:
            data = get_lotto_data(drw)
            if data:
                conn.execute('''
                    INSERT OR IGNORE INTO lotto_results
                    (drw_no, drw_no_date, num1, num2, num3, num4, num5, num6,
                     bonus_num, first_win_amnt, first_przwner_co)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?)
                ''', (
                    data['drwNo'], data['drwNoDate'],
                    data['drwtNo1'], data['drwtNo2'], data['drwtNo3'],
                    data['drwtNo4'], data['drwtNo5'], data['drwtNo6'],
                    data['bnusNo'],
                    data.get('firstWinamnt', 0),
                    data.get('firstPrzwnerCo', 0)
                ))
                saved += 1
                consecutive_failures = 0

                if (i + 1) % 5 == 0 or (i + 1) == total_targets:
                    print(f"  진행: {((i+1)/total_targets*100):.1f}% ({i+1}/{total_targets}) - {drw}회차 완료", flush=True)
                    conn.commit()

                time.sleep(1.2) # 속도보다는 안정성! (1.2초)
            else:
                consecutive_failures += 1
                wait_time = min(300, 10 * consecutive_failures) 
                print(f"  [대기] {drw}회차 실패. {wait_time}초 후 재시도... ({consecutive_failures}/5)", flush=True)
                time.sleep(wait_time)
                
                if consecutive_failures >= 5:
                    print("[중단] 연속 실패로 인해 작업을 중단합니다. 나중에 다시 시도해주세요.")
                    break
        except Exception as e:
            print(f"  [에러] {drw}회차 처리 중 오류: {e}")
            time.sleep(5)

    conn.commit()
    conn.close()
    print(f"\n[수집 종료] 이번 작업으로 {saved}개 회차가 업데이트되었습니다.")

def update_to_latest():
    """DB의 마지막 회차부터 최신 회차까지 업데이트합니다."""
    conn = sqlite3.connect(DB_PATH)
    ensure_table(conn)
    
    # DB에 저장된 가장 큰 회차 확인
    last_saved = conn.execute('SELECT MAX(drw_no) FROM lotto_results').fetchone()[0]
    if last_saved is None:
        last_saved = 0
    
    conn.close()
    
    print(f"[업데이트] DB 마지막 회차: {last_saved}회")
    collect(start_drw=last_saved + 1)

if __name__ == "__main__":
    # 실행 시 전체 데이터 수집 시도 (이미 있는 건 스킵됨)
    update_to_latest()
