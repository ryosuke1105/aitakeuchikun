/**
 * Cyber Authentication ✕ Harajuku Yume-Kawaii Q&A Web Application
 * Dynamic UI Controller & API Communication Handler
 */

document.addEventListener('DOMContentLoaded', () => {
    // DOM Element References
    const cyberScreen = document.getElementById('cyber-screen');
    const yumekawaiiScreen = document.getElementById('yumekawaii-screen');
    const noiseOverlay = document.getElementById('noise-overlay');
    const cyberAuthForm = document.getElementById('cyber-auth-form');
    const passcodeInput = document.getElementById('passcode-input');
    const cyberErrorMsg = document.getElementById('cyber-error-msg');
    const authBtn = document.getElementById('auth-btn');

    // Kawaii Screen Elements
    const kawaiiQaForm = document.getElementById('kawaii-qa-form');
    const questionInput = document.getElementById('question-input');
    const charLimitSlider = document.getElementById('char-limit-slider');
    const charLimitNumber = document.getElementById('char-limit-number');
    const askBtn = document.getElementById('ask-btn');
    const kawaiiLoading = document.getElementById('kawaii-loading');
    const answerContainer = document.getElementById('answer-container');
    const answerText = document.getElementById('answer-text');
    const charCountBadge = document.getElementById('char-count-badge');
    const docSourcesList = document.getElementById('doc-sources-list');
    const logoutBtn = document.getElementById('logout-btn');

    // =========================================================================
    // 1. SCREEN A: CYBER AUTHENTICATION HANDLER
    // =========================================================================
    
    if (cyberAuthForm) {
        cyberAuthForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const password = passcodeInput.value.trim();
            if (!password) return;

            cyberErrorMsg.textContent = '';
            authBtn.disabled = true;
            authBtn.textContent = '[ AUTHENTICATING... ]';

            try {
                const response = await fetch('/api/login', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ password })
                });

                let data;
                const contentType = response.headers.get('content-type') || '';
                if (contentType.includes('application/json')) {
                    data = await response.json();
                } else {
                    const text = await response.text();
                    throw new Error(`サーバーエラー (${response.status}): HTML応答が返されました`);
                }

                if (response.ok && data.success) {
                    triggerScreenTransition();
                } else {
                    cyberErrorMsg.textContent = `> ${data.message || 'ACCESS DENIED: INVALID PASSCODE'}`;
                    passcodeInput.value = '';
                    passcodeInput.focus();
                }
            } catch (err) {
                console.error('Authentication API error:', err);
                cyberErrorMsg.textContent = `> ${err.message || 'CRITICAL SYSTEM ERROR'}`;
            } finally {
                authBtn.disabled = false;
                authBtn.textContent = '[ AUTHENTICATE / ENTER ]';
            }
        });
    }


    /**
     * Executes the Noise Glitch Blackout Transition from Screen A to Screen B
     */
    function triggerScreenTransition() {
        noiseOverlay.classList.add('trigger-glitch');

        // Mid-glitch: Switch DOM elements and Theme classes
        setTimeout(() => {
            cyberScreen.style.display = 'none';
            document.body.className = 'yumekawaii-theme';
            yumekawaiiScreen.style.display = 'block';
            questionInput.focus();
        }, 600);

        // End-glitch: Remove noise overlay class
        setTimeout(() => {
            noiseOverlay.classList.remove('trigger-glitch');
        }, 1300);
    }


    // =========================================================================
    // 2. SCREEN B: CHARACTER SLIDER & NUMBER SYNC
    // =========================================================================

    if (charLimitSlider && charLimitNumber) {
        // Sync Range Slider -> Number Input
        charLimitSlider.addEventListener('input', (e) => {
            charLimitNumber.value = e.target.value;
        });

        // Sync Number Input -> Range Slider
        charLimitNumber.addEventListener('input', (e) => {
            let val = parseInt(e.target.value) || 300;
            if (val < 50) val = 50;
            if (val > 1000) val = 1000;
            charLimitSlider.value = val;
        });
    }


    // =========================================================================
    // 3. SCREEN B: GEMINI Q&A FORM SUBMISSION
    // =========================================================================

    if (kawaiiQaForm) {
        kawaiiQaForm.addEventListener('submit', async (e) => {
            e.preventDefault();

            const question = questionInput.value.trim();
            const maxChars = parseInt(charLimitNumber.value) || 300;

            if (!question) {
                alert('質問内容を入力してね！💖');
                return;
            }

            // Show Sparkle Loading State
            answerContainer.style.display = 'none';
            kawaiiLoading.style.display = 'block';
            askBtn.disabled = true;
            askBtn.style.opacity = '0.7';

            let attempts = 0;
            const maxAttempts = 3;
            let success = false;

            while (attempts < maxAttempts && !success) {
                attempts++;
                try {
                    const response = await fetch('/api/ask', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            question: question,
                            max_chars: maxChars
                        })
                    });

                    if (response.status === 401) {
                        alert('セッションが切れちゃった！もう一度認証してね♪');
                        location.reload();
                        return;
                    }

                    const contentType = response.headers.get('content-type') || '';
                    if (response.ok && contentType.includes('application/json')) {
                        const data = await response.json();
                        if (data.error) throw new Error(data.error);
                        renderKawaiiAnswer(data);
                        success = true;
                        break;
                    } else {
                        // If 502 or server waking up, wait 2.5s and retry automatically
                        if (attempts < maxAttempts) {
                            console.warn(`Render server waking up (attempt ${attempts}/${maxAttempts})... Retrying in 2.5s`);
                            await new Promise(r => setTimeout(r, 2500));
                            continue;
                        } else {
                            throw new Error(`サーバー準備中 (${response.status})。もう一度「質問する」を押してね！`);
                        }
                    }
                } catch (err) {
                    console.error(`Q&A attempt ${attempts} failed:`, err);
                    if (attempts < maxAttempts && (err.message.includes('Failed to fetch') || err.message.includes('502'))) {
                        await new Promise(r => setTimeout(r, 2500));
                        continue;
                    } else {
                        renderKawaiiError(err.message || '通信エラーが発生しました');
                        break;
                    }
                }
            }

            kawaiiLoading.style.display = 'none';
            askBtn.disabled = false;
            askBtn.style.opacity = '1';

        });
    }

    /**
     * Render the Answer inside the Cloud Card with Character Counter Badge
     */
    function renderKawaiiAnswer(data) {
        answerText.textContent = data.answer;

        // Character Count Badge
        const actualCount = data.char_count;
        const maxLimit = data.max_chars;
        charCountBadge.textContent = `生成結果：${actualCount}文字 / 上限 ${maxLimit}文字 ✨`;
        
        if (actualCount > maxLimit) {
            charCountBadge.classList.add('exceeded');
        } else {
            charCountBadge.classList.remove('exceeded');
        }

        // Render Source Document Tags
        docSourcesList.innerHTML = '';
        if (data.sources && data.sources.length > 0) {
            data.sources.forEach(src => {
                const tag = document.createElement('span');
                tag.className = 'doc-source-tag';
                tag.textContent = `📄 ${src}`;
                docSourcesList.appendChild(tag);
            });
        } else {
            docSourcesList.innerHTML = '<span class="doc-source-tag">📄 参照ドキュメント</span>';
        }

        answerContainer.style.display = 'block';
        answerContainer.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }

    /**
     * Render error response cleanly
     */
    function renderKawaiiError(errorMessage) {
        answerText.textContent = `😭 エラー: ${errorMessage}`;
        charCountBadge.textContent = `エラー発生`;
        docSourcesList.innerHTML = '';
        answerContainer.style.display = 'block';
    }


    // =========================================================================
    // 4. LOGOUT HANDLER
    // =========================================================================

    if (logoutBtn) {
        logoutBtn.addEventListener('click', async () => {
            try {
                await fetch('/api/logout', { method: 'POST' });
                location.reload();
            } catch (err) {
                console.error('Logout error:', err);
                location.reload();
            }
        });
    }
});
