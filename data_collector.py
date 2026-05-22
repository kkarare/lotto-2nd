"""
data_collector.py
동행복권 데이터 수집기 - HTML 스크래핑 + 폴백 데이터 혼합 방식
"""
import requests
import sqlite3
import time
import os
import re

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


# =====================================================================
# 수동 폴백 데이터 (API 차단 시 사용)
# 매주 추첨 후 여기에 추가하면 자동으로 DB에 반영됩니다!
# =====================================================================
FALLBACK_DATA = {
    1223: {
        'drwNo': 1223, 'drwNoDate': '2026-05-09',
        'drwtNo1': 16, 'drwtNo2': 18, 'drwtNo3': 20,
        'drwtNo4': 32, 'drwtNo5': 33, 'drwtNo6': 39,
        'bnusNo': 26, 'firstWinamnt': 1857554133, 'firstPrzwnerCo': 16,
        'returnValue': 'success'
    },
    1224: {
        'drwNo': 1224, 'drwNoDate': '2026-05-16',
        'drwtNo1': 9, 'drwtNo2': 18, 'drwtNo3': 21,
        'drwtNo4': 27, 'drwtNo5': 44, 'drwtNo6': 45,
        'bnusNo': 28, 'firstWinamnt': 2414850000, 'firstPrzwnerCo': 12,
        'returnValue': 'success'
    },
    # [수동 폴백 가이드] 1225회 추첨(5/23 토) 후, 아래 주석을 풀고 당첨번호를 적어주시면 즉시 서버에 반영됩니다!
    # 1225: {
    #     'drwNo': 1225, 'drwNoDate': '2026-05-23',
    #     'drwtNo1': 0, 'drwtNo2': 0, 'drwtNo3': 0,
    #     'drwtNo4': 0, 'drwtNo5': 0, 'drwtNo6': 0,
    #     'bnusNo': 0, 'firstWinamnt': 0, 'firstPrzwnerCo': 0,
    #     'returnValue': 'success'
    # },
}

# 글로벌 세션 (재사용)
session = requests.Session()
session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7',
})


def _init_session():
    """메인 페이지 방문으로 세션 쿠키 초기화"""
    try:
        session.get('https://www.dhlottery.co.kr/', timeout=10)
    except Exception:
        pass


def _scrape_draw_from_page(drw_no):
    """
    동행복권 당첨결과 페이지를 HTML 스크래핑하여 특정 회차 데이터 조회
    byWin 페이지는 드롭다운 선택으로 회차를 변경하므로 POST 방식 사용
    """
    try:
        url = 'https://www.dhlottery.co.kr/gameResult.do?method=byWin'
        r = session.post(
            url,
            data={'drwNo': str(drw_no), 'dwrNoList': str(drw_no)},
            headers={
                'Content-Type': 'application/x-www-form-urlencoded',
                'Accept': 'text/html,application/xhtml+xml',
                'Referer': url,
            },
            timeout=15
        )
        text = r.text

        # ── 회차 확인 ──────────────────────────────────────────────────
        round_match = re.search(r'(\d{4})\s*회', text)
        if not round_match or int(round_match.group(1)) != drw_no:
            return None  # 원하는 회차가 아님

        # ── 당첨번호 추출 (다양한 패턴) ─────────────────────────────────
        nums = re.findall(r'ball_645[^>]*>\s*(\d+)\s*<', text)
        if not nums:
            nums = re.findall(r'class=["\'][^"\']*num\s*win[^"\']*["\'][^>]*>\s*(\d+)\s*<', text)
        if not nums:
            # 순서 기반 파싱: "당첨번호" 뒤에 오는 숫자들
            idx = text.find('당첨번호')
            if idx < 0:
                idx = text.find('winNum')
            if idx >= 0:
                snippet = text[idx:idx+500]
                nums = re.findall(r'\b(\d{1,2})\b', snippet)
                nums = [n for n in nums if 1 <= int(n) <= 45][:7]

        if len(nums) < 7:
            return None

        # ── 날짜 추출 ──────────────────────────────────────────────────
        date_match = re.search(r'(\d{4})\.\s*(\d{2})\.\s*(\d{2})', text)
        drw_date = f"{date_match.group(1)}-{date_match.group(2)}-{date_match.group(3)}" if date_match else ''

        return {
            'drwNo': drw_no,
            'drwNoDate': drw_date,
            'drwtNo1': int(nums[0]), 'drwtNo2': int(nums[1]), 'drwtNo3': int(nums[2]),
            'drwtNo4': int(nums[3]), 'drwtNo5': int(nums[4]), 'drwtNo6': int(nums[5]),
            'bnusNo': int(nums[6]),
            'firstWinamnt': 0, 'firstPrzwnerCo': 0,
            'returnValue': 'success'
        }
    except Exception as e:
        print(f"  [스크래핑오류] {drw_no}회차: {e}", flush=True)
        return None


def _get_via_json_api(drw_no):
    """
    동행복권 JSON API 직접 호출 시도
    (현재 로그인 차단 상태이나 환경 변화 대비 유지)
    """
    url = f"https://www.dhlottery.co.kr/common.do?method=getLottoNumber&drwNo={drw_no}"
    try:
        resp = session.get(
            url,
            headers={'Accept': 'application/json, text/javascript, */*; q=0.01',
                     'X-Requested-With': 'XMLHttpRequest',
                     'Referer': 'https://www.dhlottery.co.kr/gameInfo.do?method=lotto645'},
            timeout=15
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        if data.get('returnValue') == 'success':
            return data
    except Exception:
        pass
    return None


def get_lotto_data(drw_no):
    """
    특정 회차 데이터 조회 - 우선순위:
    1. 수동 폴백 데이터 (가장 신뢰)
    2. JSON API (빠르고 정확)
    3. HTML 스크래핑 (API 차단 시 대안)
    """
    # 1. 수동 폴백 데이터
    if drw_no in FALLBACK_DATA:
        print(f"  [폴백] {drw_no}회차 데이터를 수동 저장 데이터로 로드합니다.", flush=True)
        return FALLBACK_DATA[drw_no]

    # 2. JSON API 시도
    data = _get_via_json_api(drw_no)
    if data:
        print(f"  [API] {drw_no}회차 JSON API 성공!", flush=True)
        return data

    # 3. HTML 스크래핑 시도
    data = _scrape_draw_from_page(drw_no)
    if data:
        print(f"  [스크래핑] {drw_no}회차 HTML 스크래핑 성공!", flush=True)
        return data

    return None


def find_latest_draw(start_hint=1160):
    """
    DB 마지막 회차(start_hint)부터 탐색하여 최신 회차 확인

    1. 폴백 데이터에서 최대 회차 먼저 확인 (즉시, 0 API 호출)
    2. 그 이후 API/스크래핑으로 탐색
    """
    # 폴백 데이터의 최대 회차 확인
    fallback_max = max(FALLBACK_DATA.keys()) if FALLBACK_DATA else 0

    if fallback_max >= start_hint:
        print(f"[탐색] 폴백 데이터 최신 회차: {fallback_max}회 (start_hint: {start_hint})")
        # 폴백 이후 회차도 API로 확인
        curr = fallback_max
    else:
        curr = max(start_hint, 1)

    print(f"[탐색] API로 추가 최신 회차 확인 중... (시작: {curr}회)")
    max_fail = 3
    fail_count = 0

    while fail_count < max_fail:
        data = get_lotto_data(curr + 1)
        if data:
            curr += 1
            fail_count = 0
        else:
            fail_count += 1
            if fail_count < max_fail:
                time.sleep(1.0)

    print(f"[탐색 완료] 최신 회차: {curr}회")
    return curr


def collect(start_drw=1, years=None, search_from=None):
    """지정한 범위의 데이터를 수집합니다."""
    conn = sqlite3.connect(DB_PATH)
    ensure_table(conn)

    # 최신 회차 탐색
    hint = search_from if search_from is not None else max(start_drw - 1, 1)
    latest = find_latest_draw(hint)
    if latest < 1:
        print("[오류] 최신 회차 탐색 실패. 네트워크를 확인해주세요.")
        conn.close()
        return

    # 수집 시작점
    if years:
        count_to_collect = years * 52
        start = max(1, latest - count_to_collect + 1)
    else:
        start = start_drw

    # 중복 제외
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

                # 폴백 데이터는 딜레이 없이, API/스크래핑은 1.0초 대기
                if drw not in FALLBACK_DATA:
                    time.sleep(1.0)
            else:
                consecutive_failures += 1
                wait_time = min(300, 10 * consecutive_failures)
                print(f"  [대기] {drw}회차 실패. {wait_time}초 후 재시도... ({consecutive_failures}/5)", flush=True)
                time.sleep(wait_time)

                if consecutive_failures >= 5:
                    print("[중단] 연속 실패로 인해 작업을 중단합니다.")
                    break
        except Exception as e:
            print(f"  [에러] {drw}회차 처리 중 오류: {e}")
            time.sleep(5)

    conn.commit()
    conn.close()
    print(f"\n[수집 종료] 이번 작업으로 {saved}개 회차가 업데이트되었습니다.")


def update_to_latest():
    """DB의 마지막 회차부터 최신 회차까지 업데이트합니다."""
    # 세션 초기화 (쿠키 획득)
    _init_session()

    conn = sqlite3.connect(DB_PATH)
    ensure_table(conn)

    # DB 최신 회차 확인
    last_saved = conn.execute('SELECT MAX(drw_no) FROM lotto_results').fetchone()[0]
    if last_saved is None:
        last_saved = 0
    conn.close()

    print(f"[업데이트] DB 마지막 회차: {last_saved}회")

    # 이미 최신이면 스킵
    fallback_max = max(FALLBACK_DATA.keys()) if FALLBACK_DATA else 0
    if last_saved >= fallback_max:
        print(f"[확인] DB({last_saved}회) >= 폴백최신({fallback_max}회), API로 추가 확인...")
    else:
        print(f"[확인] DB({last_saved}회) < 폴백최신({fallback_max}회), 업데이트 필요!")

    collect(start_drw=last_saved + 1, search_from=max(last_saved, 1))


def fix_corrupted_data():
    """
    잘못 저장된 데이터 수정 (수학적 공식을 이용한 즉시 복구)
    """
    import datetime
    conn = sqlite3.connect(DB_PATH)
    ensure_table(conn)

    # 1회차 기준일: 2002년 12월 7일
    start_date = datetime.date(2002, 12, 7)

    # 날짜가 비정상인 레코드 찾기 (보통 '2026-05-16'처럼 10자여야 함)
    bad_rows = conn.execute(
        "SELECT drw_no FROM lotto_results WHERE length(drw_no_date) != 10 OR drw_no_date IS NULL"
    ).fetchall()

    if not bad_rows:
        print("[점검] 손상된 데이터 없음.")
        conn.close()
        return

    print(f"[수정] 손상된 {len(bad_rows)}개 레코드 발견! 수학적 공식으로 즉시 복구합니다...")
    for (drw_no,) in bad_rows:
        calculated_date = start_date + datetime.timedelta(days=(drw_no - 1) * 7)
        date_str = calculated_date.strftime('%Y-%m-%d')
        conn.execute(
            "UPDATE lotto_results SET drw_no_date=? WHERE drw_no=?",
            (date_str, drw_no)
        )

    conn.commit()
    conn.close()
    print("[수정 완료] 모든 회차의 날짜 정보가 정상 복구되었습니다!")


if __name__ == "__main__":
    # 1. 손상 데이터 먼저 수정
    fix_corrupted_data()
    # 2. 최신 데이터 업데이트
    update_to_latest()
