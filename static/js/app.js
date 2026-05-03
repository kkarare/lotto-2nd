document.addEventListener('DOMContentLoaded', () => {
    // --- 상태 관리 ---
    const state = {
        currentTab: 'home',
        includeNums: [],
        excludeNums: [],
        lastGenerated: null,
        status: { online: false, latest_draw: null }
    };

    // --- DOM 요소 ---
    const tabs = document.querySelectorAll('.tab-link');
    const contents = document.querySelectorAll('.tab-content');
    const statusBadge = document.getElementById('app-status');
    const btnGenerate = document.getElementById('btn-generate');
    const btnSave = document.getElementById('btn-save');
    const genDisplay = document.getElementById('generated-numbers');
    const filterGrid = document.getElementById('filter-grid');
    const includeTags = document.getElementById('include-tags');
    const excludeTags = document.getElementById('exclude-tags');
    const btnResetFilter = document.getElementById('btn-reset-filter');

    // --- 초기화 ---
    init();

    function init() {
        bindEvents();
        createFilterGrid();
        checkStatus();
        requestNotificationPermission();
        setInterval(checkStatus, 30000);
    }

    // --- 알림 권한 요청 ---
    function requestNotificationPermission() {
        if ('Notification' in window && Notification.permission === 'default') {
            Notification.requestPermission();
        }
    }

    function showNotification(title, body) {
        if ('Notification' in window && Notification.permission === 'granted') {
            new Notification(title, { body, icon: '/static/icons/icon-192x192.png' });
        }
    }

    // --- 이벤트 바인딩 ---
    function bindEvents() {
        tabs.forEach(tab => {
            tab.addEventListener('click', (e) => {
                e.preventDefault();
                switchTab(tab.dataset.tab);
            });
        });
        btnGenerate.addEventListener('click', generateNumbers);
        btnSave.addEventListener('click', saveCurrentNumbers);

        // 엑셀 업로드 버튼
        const btnUploadExcel = document.getElementById('btn-upload-excel');
        if (btnUploadExcel) {
            btnUploadExcel.addEventListener('click', uploadExcel);
        }

        // 필터 초기화 버튼
        if (btnResetFilter) {
            btnResetFilter.addEventListener('click', resetFilter);
        }

        // 수동 업데이트 버튼
        const btnManualUpdate = document.getElementById('btn-manual-update');
        if (btnManualUpdate) {
            btnManualUpdate.addEventListener('click', manualUpdate);
        }
    }

    // --- 탭 전환 ---
    function switchTab(tabId) {
        state.currentTab = tabId;
        tabs.forEach(t => t.classList.toggle('active', t.dataset.tab === tabId));
        contents.forEach(c => c.classList.toggle('active', c.id === `tab-${tabId}`));

        if (tabId === 'saved') loadSavedNumbers();
        if (tabId === 'stats') loadStats();
        if (tabId === 'check') loadWinResults();
    }

    // --- 앱 상태 확인 ---
    async function checkStatus() {
        try {
            const res = await fetch('/api/status');
            if (!res.ok) throw new Error('Server unreachable');
            const data = await res.json();
            state.status = data;
            statusBadge.textContent = data.latest_draw
                ? `✅ ${data.latest_draw}회차 연결됨`
                : '📡 데이터 준비 중...';
            statusBadge.style.background = 'var(--success-light)';
            statusBadge.style.color = 'var(--success)';
        } catch (e) {
            statusBadge.textContent = '⚠️ 오프라인 모드';
            statusBadge.style.background = '#FEE2E2';
            statusBadge.style.color = '#B91C1C';
            console.log('Status check failed: Using offline fallback');
        }
    }

    // --- 필터 그리드 생성 (1~45) ---
    function createFilterGrid() {
        filterGrid.innerHTML = '';
        for (let i = 1; i <= 45; i++) {
            const item = document.createElement('div');
            item.className = 'grid-item';
            item.textContent = i;
            item.dataset.num = i;
            item.addEventListener('click', () => toggleFilter(i, item));
            filterGrid.appendChild(item);
        }
    }

    // --- 필터 토글 (포함→제외→해제) ---
    function toggleFilter(num, element) {
        if (state.includeNums.includes(num)) {
            // 포함 → 제외
            state.includeNums = state.includeNums.filter(n => n !== num);
            if (state.excludeNums.length < 5) {
                state.excludeNums.push(num);
                element.className = 'grid-item exclude';
            } else {
                element.className = 'grid-item';
            }
        } else if (state.excludeNums.includes(num)) {
            // 제외 → 해제
            state.excludeNums = state.excludeNums.filter(n => n !== num);
            element.className = 'grid-item';
        } else {
            // 해제 → 포함 (최대 3개)
            if (state.includeNums.length < 3) {
                state.includeNums.push(num);
                element.className = 'grid-item include';
            } else if (state.excludeNums.length < 5) {
                state.excludeNums.push(num);
                element.className = 'grid-item exclude';
            }
        }
        updateFilterTags();
    }

    function updateFilterTags() {
        includeTags.innerHTML = state.includeNums
            .map(n => `<span style="background:var(--success);color:white;padding:3px 9px;border-radius:12px;font-size:0.8rem;margin:2px;">${n}</span>`)
            .join('');
        excludeTags.innerHTML = state.excludeNums
            .map(n => `<span style="background:var(--danger);color:white;padding:3px 9px;border-radius:12px;font-size:0.8rem;margin:2px;">${n}</span>`)
            .join('');
    }

    // --- 필터 초기화 ---
    function resetFilter() {
        state.includeNums = [];
        state.excludeNums = [];
        document.querySelectorAll('.grid-item').forEach(el => el.className = 'grid-item');
        updateFilterTags();
    }

    // --- AI 번호 생성 ---
    async function generateNumbers() {
        btnGenerate.disabled = true;
        genDisplay.innerHTML = '<div class="ball-placeholder">🤖 AI 분석 중...</div>';
        document.getElementById('prediction-info').style.display = 'none';

        try {
            const res = await fetch('/api/generate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ include: state.includeNums, exclude: state.excludeNums })
            });
            
            if (!res.ok) throw new Error('Network response was not ok');
            
            const data = await res.json();
            if (data.success) {
                renderGenerated(data.combinations[0]);
            } else {
                throw new Error(data.error || 'Generation failed');
            }
        } catch (e) {
            console.warn('Offline mode: Generating numbers locally');
            // 오프라인 로컬 생성 로직
            const localNums = generateLocalNumbers(state.includeNums, state.excludeNums);
            const localResult = {
                numbers: localNums,
                score: Math.floor(Math.random() * 20) + 60, // 60~80점
                analysis: '⚠️ 오프라인 모드입니다. 서버 연결 시 더 정밀한 AI 분석이 가능합니다.'
            };
            renderGenerated(localResult);
            showToast('⚠️ 오프라인 모드로 생성되었습니다.');
        } finally {
            btnGenerate.disabled = false;
        }
    }

    function renderGenerated(data) {
        renderBalls(data.numbers);
        state.lastGenerated = data;
        setTimeout(() => {
            document.getElementById('prediction-info').style.display = 'block';
            document.getElementById('prediction-score').textContent = `${data.score}%`;
            document.getElementById('analysis-text').textContent = data.analysis;
        }, 700);
        btnSave.disabled = false;
        showNotification('🍀 번호 생성 완료!', '오늘의 행운 번호가 도착했습니다.');
    }

    function generateLocalNumbers(include, exclude) {
        const nums = new Set(include);
        while (nums.size < 6) {
            const n = Math.floor(Math.random() * 45) + 1;
            if (!exclude.includes(n)) nums.add(n);
        }
        return Array.from(nums).sort((a, b) => a - b);
    }

    // --- 로또볼 렌더링 (순차 애니메이션) ---
    function renderBalls(numbers) {
        genDisplay.innerHTML = '';
        numbers.forEach((num, index) => {
            setTimeout(() => {
                const ball = document.createElement('div');
                ball.className = `lotto-ball ${getBallColorClass(num)}`;
                ball.textContent = num;
                genDisplay.appendChild(ball);
            }, index * 120);
        });
    }

    function getBallColorClass(num) {
        if (num <= 10) return 'ball-yellow';
        if (num <= 20) return 'ball-blue';
        if (num <= 30) return 'ball-red';
        if (num <= 40) return 'ball-gray';
        return 'ball-green';
    }

    // --- 번호 저장 ---
    async function saveCurrentNumbers() {
        if (!state.lastGenerated) return;
        
        const saveData = {
            ...state.lastGenerated,
            id: Date.now(), // 로컬용 임시 ID
            date: new Date().toISOString().split('T')[0],
            is_purchased: false,
            win_rank: 0,
            is_local: true // 로컬 저장 표시
        };

        try {
            const res = await fetch('/api/save', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(state.lastGenerated)
            });
            const data = await res.json();
            if (data.success) {
                showToast('💾 서버에 저장되었습니다! 🍀');
                btnSave.disabled = true;
                showNotification('저장 완료!', '행운의 번호가 서버에 안전하게 저장되었습니다.');
                return;
            }
        } catch (e) {
            console.warn('Server save failed, falling back to localStorage');
        }

        // 오프라인/서버 실패 시 로컬 저장
        const localSaved = JSON.parse(localStorage.getItem('lucky_saved_numbers') || '[]');
        localSaved.unshift(saveData);
        localStorage.setItem('lucky_saved_numbers', JSON.stringify(localSaved.slice(0, 50))); // 최대 50개 유지
        
        showToast('📱 내 휴대폰에 저장되었습니다! (오프라인)');
        btnSave.disabled = true;
        showNotification('로컬 저장 완료!', '컴퓨터가 꺼져 있어 내 휴대폰에 임시 저장했습니다.');
    }

    // --- 토스트 메시지 ---
    function showToast(msg) {
        const toast = document.createElement('div');
        toast.textContent = msg;
        toast.style.cssText = `
            position:fixed; bottom:85px; left:50%; transform:translateX(-50%);
            background:#1E293B; color:white; padding:10px 20px;
            border-radius:20px; font-size:0.9rem; font-weight:600;
            z-index:9999; animation:fadeIn 0.3s ease;
            white-space:nowrap;
        `;
        document.body.appendChild(toast);
        setTimeout(() => toast.remove(), 2500);
    }

    // --- 저장함 로드 ---
    async function loadSavedNumbers() {
        const savedList = document.getElementById('saved-list');
        savedList.innerHTML = '<p class="empty-msg">불러오는 중...</p>';
        
        let allSaved = [];
        
        // 1. 로컬 저장 데이터 먼저 가져오기
        const localSaved = JSON.parse(localStorage.getItem('lucky_saved_numbers') || '[]');
        allSaved = [...localSaved];

        // 2. 서버 데이터 가져오기 시도
        try {
            const res = await fetch('/api/saved');
            const data = await res.json();
            if (data.success && data.saved.length > 0) {
                // 중복 방지 (번호 조합이 같으면 서버 데이터 우선)
                const serverNums = data.saved.map(s => s.numbers.join(','));
                allSaved = [
                    ...data.saved,
                    ...localSaved.filter(l => !serverNums.includes(l.numbers.join(',')))
                ];
            }
        } catch (e) {
            console.log('Using local data only (Offline)');
        }

        if (allSaved.length > 0) {
            savedList.innerHTML = allSaved.map(item => `
                <div style="background:white; border-radius:16px; padding:15px; margin-bottom:10px; box-shadow:0 2px 8px rgba(0,0,0,0.06); position:relative;">
                    ${item.is_local ? '<span style="position:absolute; top:10px; right:10px; font-size:0.65rem; color:var(--primary); background:var(--primary-light); padding:2px 5px; border-radius:4px;">내 폰 저장</span>' : ''}
                    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
                        <span style="font-size:0.8rem; color:var(--text-sub);">📅 ${item.date}</span>
                        <span style="font-size:0.78rem; font-weight:700; background:var(--primary-light); color:var(--primary); padding:3px 8px; border-radius:10px;">
                            ${item.win_rank > 0 ? '🏆 ' + item.win_rank + '등 당첨!' : '⏳ 대기'}
                        </span>
                    </div>
                    <div style="display:flex; gap:6px; flex-wrap:wrap;">
                        ${item.numbers.map(n => `
                            <div class="${getBallColorClass(n)}" style="width:32px;height:32px;border-radius:50%;display:flex;align-items:center;justify-content:center;color:white;font-size:0.78rem;font-weight:800;">
                                ${n}
                            </div>
                        `).join('')}
                    </div>
                </div>
            `).join('');
        } else {
            savedList.innerHTML = '<p class="empty-msg">저장된 번호가 없습니다.</p>';
        }
    }

    // --- 통계 로드 ---
    async function loadStats() {
        const hotDisplay = document.getElementById('hot-numbers');
        const coldDisplay = document.getElementById('cold-numbers');
        hotDisplay.innerHTML = '<span style="color:var(--text-sub);font-size:0.85rem;">불러오는 중...</span>';
        coldDisplay.innerHTML = '<span style="color:var(--text-sub);font-size:0.85rem;">불러오는 중...</span>';
        try {
            const res = await fetch('/api/stats');
            const data = await res.json();
            if (data.success) {
                if (data.analysis.hot && data.analysis.hot.length > 0) {
                    hotDisplay.innerHTML = data.analysis.hot
                        .map(n => `<div class="${getBallColorClass(n)}" style="width:32px;height:32px;border-radius:50%;display:inline-flex;align-items:center;justify-content:center;color:white;font-size:0.78rem;font-weight:800;margin:2px;">${n}</div>`)
                        .join('');
                } else {
                    const msg = data.analysis.message || '📡 데이터 수집 중... (data_collector.py 실행 필요)';
                    hotDisplay.innerHTML = `<span style="color:var(--text-sub);font-size:0.82rem;">${msg}</span>`;
                }
                if (data.analysis.cold && data.analysis.cold.length > 0) {
                    coldDisplay.innerHTML = data.analysis.cold
                        .map(n => `<div class="${getBallColorClass(n)}" style="width:32px;height:32px;border-radius:50%;display:inline-flex;align-items:center;justify-content:center;color:white;font-size:0.78rem;font-weight:800;margin:2px;">${n}</div>`)
                        .join('');
                } else {
                    coldDisplay.innerHTML = '<span style="color:var(--text-sub);font-size:0.82rem;">📡 데이터 수집 후 표시됩니다</span>';
                }
            } else {
                hotDisplay.innerHTML = '<span style="color:var(--text-sub);font-size:0.85rem;">데이터 수집 중...</span>';
                coldDisplay.innerHTML = '<span style="color:var(--text-sub);font-size:0.85rem;">데이터 수집 중...</span>';
            }
        } catch (e) {
            hotDisplay.innerHTML = '<span style="color:var(--text-sub);">⚠️ 서버 연결 확인 필요</span>';
            coldDisplay.innerHTML = '<span style="color:var(--text-sub);">⚠️ 서버 연결 확인 필요</span>';
        }
    }

    // --- 당첨확인 로드 ---
    async function loadWinResults() {
        const info = document.getElementById('latest-draw-info');
        const resultArea = document.getElementById('win-check-results');
        if (state.status.latest_draw) {
            info.innerHTML = `
                <h4 style="margin:0 0 5px 0;">🎱 최신 ${state.status.latest_draw}회차</h4>
                <p style="font-size:0.85rem;color:var(--text-sub);margin:0;">저장된 번호의 당첨 여부를 자동으로 대조합니다.</p>
            `;
        } else {
            info.innerHTML = '<p style="margin:0; color:var(--text-sub); font-size:0.9rem;">데이터 수집 완료 후 이용 가능합니다.</p>';
        }

        // 저장된 번호 목록을 당첨확인 영역에도 표시
        resultArea.innerHTML = '';
        try {
            const res = await fetch('/api/saved');
            const data = await res.json();
            if (data.success && data.saved.length > 0) {
                resultArea.innerHTML = `<p style="font-size:0.85rem; color:var(--text-sub); margin-bottom:10px;">📋 저장된 ${data.saved.length}개 조합</p>` +
                    data.saved.map(item => `
                        <div style="background:white; border-radius:16px; padding:15px; margin-bottom:10px; box-shadow:0 2px 8px rgba(0,0,0,0.06);">
                            <div style="display:flex; gap:6px; flex-wrap:wrap;">
                                ${item.numbers.map(n => `
                                    <div class="${getBallColorClass(n)}" style="width:32px;height:32px;border-radius:50%;display:flex;align-items:center;justify-content:center;color:white;font-size:0.78rem;font-weight:800;">
                                        ${n}
                                    </div>
                                `).join('')}
                            </div>
                        </div>
                    `).join('');
            } else {
                resultArea.innerHTML = '<p class="empty-msg">저장된 번호가 없습니다.</p>';
            }
        } catch (e) {
            resultArea.innerHTML = '<p class="empty-msg">⚠️ 오류</p>';
        }
    }
    // --- 엑셀 업로드 ---
    async function uploadExcel() {
        const fileInput = document.getElementById('excel-file');
        const file = fileInput.files[0];
        if (!file) {
            showToast('❌ 파일을 선택해주세요!');
            return;
        }

        const btn = document.getElementById('btn-upload-excel');
        btn.disabled = true;
        btn.textContent = '⏳ 처리 중...';

        const formData = new FormData();
        formData.append('file', file);

        try {
            const res = await fetch('/api/upload_excel', {
                method: 'POST',
                body: formData
            });
            const data = await res.json();
            if (data.success) {
                showToast(`✅ ${data.count}개의 회차가 추가되었습니다!`);
                fileInput.value = '';
                checkStatus(); // 상태 갱신
                loadStats();   // 통계 갱신
            } else {
                showToast('❌ 업로드 실패: ' + data.error);
            }
        } catch (e) {
            showToast('❌ 서버 연결 오류');
        } finally {
            btn.disabled = false;
            btn.textContent = '업로드';
        }
    }

    // --- 수동 데이터 업데이트 ---
    async function manualUpdate() {
        const btn = document.getElementById('btn-manual-update');
        if (!btn) return;

        btn.disabled = true;
        const originalText = btn.textContent;
        btn.textContent = '⏳ 데이터 수집 중... (약 10~30초 소요)';

        try {
            const res = await fetch('/api/admin/update_data', { method: 'POST' });
            const data = await res.json();
            if (data.success) {
                showToast('🚀 최신 데이터 수집 완료! 🍀');
                checkStatus();
                loadStats();
            } else {
                showToast('❌ 업데이트 실패: ' + data.error);
            }
        } catch (e) {
            showToast('❌ 서버 연결 오류 (인터넷 확인)');
        } finally {
            btn.disabled = false;
            btn.textContent = originalText;
        }
    }
});
