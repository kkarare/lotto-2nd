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


def get_lotto_data(drw_no):
    """특정 회차 데이터 조회 (User-Agent 추가하여 차단 방지)"""
    url = f"https://www.dhlottery.co.kr/common.do?method=getLottoNumber&drwNo={drw_no}"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code != 200:
            return None
        data = resp.json()
        if data.get('returnValue') == 'success':
            return data
    except Exception:
        pass
    return None

def find_latest_draw():
    """1150회부터 순차 탐색으로 최신 회차 확인"""
    print("[탐색] 최신 회차 확인 중...")
    curr = 1100
    while True:
        data = get_lotto_data(curr + 1)
        if data:
            curr += 1
        else:
            # 일시적 오류 방지: 한 번 더 확인
            time.sleep(0.5)
            data2 = get_lotto_data(curr + 1)
            if data2:
                curr += 1
            else:
                break
    print(f"[탐색 완료] 최신 회차: {curr}회")
    return curr

def collect(start_drw=1, years=None):
    """
    지정한 범위의 데이터를 수집합니다.
    years가 지정되면 최신 회차부터 해당 기간만큼 역산하여 수집합니다.
    """
    conn = sqlite3.connect(DB_PATH)
    ensure_table(conn)

    latest = find_latest_draw()
    if latest < 1:
        print("[오류] 최신 회차 탐색 실패. 네트워크를 확인해주세요.")
        conn.close()
        return

    if years:
        count_to_collect = years * 52
        start = max(1, latest - count_to_collect + 1)
    else:
        start = start_drw

    total_to_fetch = latest - start + 1
    print(f"[수집 범위] {start}회 ~ {latest}회 (총 {total_to_fetch}회차)\n")

    saved = 0
    skipped = 0
    for i, drw in enumerate(range(start, latest + 1)):
        # 이미 있으면 스킵
        exists = conn.execute(
            'SELECT 1 FROM lotto_results WHERE drw_no = ?', (drw,)
        ).fetchone()
        if exists:
            skipped += 1
            continue

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

                # 진행률 표시
                progress = ((i + 1) / total_to_fetch) * 100
                if (i + 1) % 10 == 0 or (i + 1) == total_to_fetch:
                    print(f"  진행 중: {progress:.1f}% ({i+1}/{total_to_fetch}) - {drw}회차 완료", flush=True)
                    conn.commit()

                time.sleep(0.7) # 차단 방지를 위해 살짝 더 여유 있게
            else:
                print(f"  [경고] {drw}회차 데이터 수집 실패 (건너뜀)", flush=True)
                time.sleep(1.0)
        except Exception as e:
            print(f"  [에러] {drw}회차 처리 중 오류 발생: {e}", flush=True)
            time.sleep(2.0)

    conn.commit()
    conn.close()
    print(f"\n[수집 완료] 신규 저장: {saved}회차 (중복 스킵: {skipped}회차)", flush=True)

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
