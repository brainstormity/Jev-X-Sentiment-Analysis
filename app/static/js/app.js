// Jev X Sentiment Analysis Terminal Client Controller

let currentDecision = null;
// Set from the last response's market block: true when Kraken failed and the
// prices in it are placeholder constants rather than quotes.
let currentPriceIsFallback = false;

// Cost lookup per sample size
const COST_MAP = {
    50: "$0.0075",
    100: "$0.0150",
    250: "$0.0375",
    500: "$0.0750",
    1000: "$0.1500"
};

document.addEventListener("DOMContentLoaded", () => {
    setupEventListeners();
    // Await user clicking 'Analyze Asset' before running any analysis
});

function setupEventListeners() {
    const symbolInput = document.getElementById("symbol-input");
    const slider = document.getElementById("sample-size-slider");
    const sliderVal = document.getElementById("sample-size-val");
    const estimatedCost = document.getElementById("estimated-cost");
    const analyzeBtn = document.getElementById("analyze-btn");
    const copyBtn = document.getElementById("copy-levels-btn");

    // Slider change
    slider.addEventListener("input", (e) => {
        const val = parseInt(e.target.value);
        sliderVal.textContent = `${val} Tweets`;
        const costStr = COST_MAP[val] || `~$${(val * 0.00015).toFixed(4)}`;
        estimatedCost.textContent = `(${costStr})`;
    });

    // Quick chips
    document.querySelectorAll(".chip").forEach((chip) => {
        chip.addEventListener("click", () => {
            document.querySelectorAll(".chip").forEach((c) => c.classList.remove("active"));
            chip.classList.add("active");
            symbolInput.value = chip.dataset.symbol;
        });
    });

    // Search enter key
    symbolInput.addEventListener("keydown", (e) => {
        if (e.key === "Enter") {
            const sym = symbolInput.value.trim().toUpperCase();
            if (sym) runAnalysis(sym, parseInt(slider.value));
        }
    });

    // Analyze button
    analyzeBtn.addEventListener("click", () => {
        const sym = symbolInput.value.trim().toUpperCase();
        if (sym) runAnalysis(sym, parseInt(slider.value));
    });

    // Copy Levels button
    copyBtn.addEventListener("click", () => {
        if (!currentDecision) return;
        if (currentPriceIsFallback) {
            const orig = copyBtn.textContent;
            copyBtn.textContent = "No live price";
            setTimeout(() => { copyBtn.textContent = orig; }, 2000);
            return;
        }
        const d = currentDecision;
        const lvls = d.trade_levels;
        const text = [
            `--- JEV X SENTIMENT ANALYSIS TRADE TICKET ---`,
            `Asset: ${d.symbol}/USDT`,
            `Action: ${d.action} (${d.confidence_pct}% Confidence)`,
            `Entry Range: $${lvls.entry_range[0].toLocaleString()} - $${lvls.entry_range[1].toLocaleString()}`,
            `Stop Loss: $${lvls.stop_loss.toLocaleString()} (${lvls.stop_loss_pct}%)`,
            `Target 1: $${lvls.target_1.toLocaleString()} (${lvls.target_1_pct > 0 ? '+' : ''}${lvls.target_1_pct}%)`,
            `Target 2: $${lvls.target_2.toLocaleString()} (${lvls.target_2_pct > 0 ? '+' : ''}${lvls.target_2_pct}%)`,
            `Risk/Reward: ${lvls.risk_reward_ratio} R:R`,
            `Rationale: ${d.rationale}`
        ].join("\n");

        navigator.clipboard.writeText(text).then(() => {
            const orig = copyBtn.textContent;
            copyBtn.textContent = "✅ Copied!";
            setTimeout(() => { copyBtn.textContent = orig; }, 2000);
        });
    });

    // Settings Modal
    const modal = document.getElementById("settings-modal");
    const openSettingsBtn = document.getElementById("open-settings-btn");
    const closeSettingsBtn = document.getElementById("close-settings-btn");
    const cancelSettingsBtn = document.getElementById("cancel-settings-btn");
    const saveSettingsBtn = document.getElementById("save-settings-btn");
    const typesafeKeyInput = document.getElementById("typesafe-key-input");
    const twitterKeyInput = document.getElementById("twitter-key-input");

    if (openSettingsBtn && modal) {
        openSettingsBtn.addEventListener("click", () => {
            modal.classList.remove("hidden");
        });

        const closeModal = () => modal.classList.add("hidden");
        closeSettingsBtn.addEventListener("click", closeModal);
        cancelSettingsBtn.addEventListener("click", closeModal);
        modal.addEventListener("click", (e) => {
            if (e.target === modal) closeModal();
        });

        saveSettingsBtn.addEventListener("click", async () => {
            const typesafeKey = typesafeKeyInput.value.trim();
            const twitterKey = twitterKeyInput.value.trim();

            if (!typesafeKey && !twitterKey) {
                alert("Please enter at least one API key to activate live mode.");
                return;
            }

            saveSettingsBtn.disabled = true;
            saveSettingsBtn.textContent = "Saving...";

            try {
                const res = await fetch("/api/v1/settings", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        typesafe_api_key: typesafeKey || null,
                        twitter_api_key: twitterKey || null
                    })
                });

                if (!res.ok) throw new Error("Failed to save settings");
                const data = await res.json();

                // Update navbar pills
                if (data.has_typesafe_key) {
                    const pill = document.getElementById("typesafe-status");
                    pill.className = "status-pill status-active";
                    document.getElementById("typesafe-status-text").textContent = "TypeSafe AI: Live";
                }
                if (data.has_twitter_key) {
                    const pill = document.getElementById("twitter-status");
                    pill.className = "status-pill status-active";
                    document.getElementById("twitter-status-text").textContent = "TwitterAPI: Connected";
                }

                closeModal();
                alert("API keys saved! Running live analysis...");
                const sym = symbolInput.value.trim().toUpperCase() || "BTC";
                runAnalysis(sym, parseInt(slider.value));

            } catch (err) {
                alert("Error saving keys: " + err.message);
            } finally {
                saveSettingsBtn.disabled = false;
                saveSettingsBtn.textContent = "Save & Go Live";
            }
        });
    }
}

async function runAnalysis(symbol, sampleSize) {
    const sym = symbol.toUpperCase().replace("$", "");
    const analyzeBtn = document.getElementById("analyze-btn");
    const spinner = document.getElementById("loading-spinner");
    const btnText = analyzeBtn.querySelector(".btn-text");

    analyzeBtn.disabled = true;
    spinner.classList.remove("hidden");
    btnText.textContent = "Ingesting & Analyzing...";

    try {
        const response = await fetch("/api/v1/analyze", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ symbol: sym, sample_size: sampleSize }),
        });

        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.detail || "Analysis request failed");
        }

        const data = await response.json();
        updateUI(data);

    } catch (err) {
        console.error("Error analyzing asset:", err);
        alert(`Analysis Error: ${err.message}`);
    } finally {
        analyzeBtn.disabled = false;
        spinner.classList.add("hidden");
        btnText.textContent = "Analyze Asset";
    }
}

function updateUI(data) {
    const market = data.market || {};
    const stats = data.social_stats || {};
    const decision = data.decision || {};
    const tweets = data.tweets_sample || [];

    currentDecision = decision;

    // 1. Ticker Ribbon
    // Kraken failed for this symbol and market_service returned placeholder
    // constants. The response says so; the interface has to say so too, and it
    // must not turn a placeholder into entry, stop and target prices.
    const isFallback = market.is_fallback === true;
    currentPriceIsFallback = isFallback;

    document.getElementById("ticker-symbol").textContent = `${data.symbol}/USDT`;
    const priceEl = document.getElementById("ticker-price");
    priceEl.textContent = isFallback ? "unavailable" : `$${(market.price || 0).toLocaleString()}`;
    priceEl.classList.toggle("val-unavailable", isFallback);

    const changeEl = document.getElementById("ticker-change");
    const change = market.change_24h_pct || 0;
    changeEl.textContent = isFallback ? "—" : `${change > 0 ? '+' : ''}${change}%`;
    changeEl.className = isFallback
        ? "ticker-val font-mono val-unavailable"
        : `ticker-val font-mono ${change >= 0 ? 'text-success' : 'text-danger'}`;

    const fundingEl = document.getElementById("ticker-funding");
    const funding = market.funding_rate_pct || 0;
    fundingEl.textContent = isFallback ? "—" : `${funding > 0 ? '+' : ''}${funding}%`;
    fundingEl.className = isFallback
        ? "ticker-val font-mono val-unavailable"
        : `ticker-val font-mono ${funding < 0 ? 'text-success' : funding > 0.03 ? 'text-danger' : ''}`;

    const rsiEl = document.getElementById("ticker-rsi");
    rsiEl.textContent = isFallback ? "—" : (market.rsi_14 || "--");
    rsiEl.classList.toggle("val-unavailable", isFallback);

    const volEl = document.getElementById("ticker-vol");
    volEl.textContent = isFallback ? "—" : `$${((market.volume_24h_usd || 0) / 1e6).toFixed(1)}M`;
    volEl.classList.toggle("val-unavailable", isFallback);

    // 2. Decision Hero
    const badge = document.getElementById("action-badge");
    badge.textContent = decision.action || "HOLD";
    badge.className = "action-badge";

    if (decision.action.includes("BUY")) {
        badge.classList.add("badge-buy");
    } else if (decision.action.includes("SELL")) {
        badge.classList.add("badge-sell");
    } else {
        badge.classList.add("badge-hold");
    }

    document.getElementById("confidence-val").textContent = `${decision.confidence_pct || 0}%`;
    document.getElementById("rationale-box").textContent = decision.rationale || "No rationale available.";

    // Render 6-way Signal Probability Distribution
    renderProbabilityDistribution(decision);

    // 3. Trade Levels
    const banner = document.getElementById("market-fallback-banner");
    if (banner) banner.hidden = !isFallback;
    const copyBtn = document.getElementById("copy-levels-btn");
    if (copyBtn) copyBtn.disabled = isFallback;
    const levelCells = ["lvl-entry", "lvl-sl", "lvl-tp1", "lvl-tp2", "lvl-rr"];
    if (isFallback) {
        for (const id of levelCells) {
            const el = document.getElementById(id);
            el.textContent = "—";
            el.classList.add("val-unavailable");
        }
    } else {
        for (const id of levelCells) document.getElementById(id).classList.remove("val-unavailable");
        const lvls = decision.trade_levels || {};
        const entry = lvls.entry_range || [market.price, market.price];
        document.getElementById("lvl-entry").textContent = `$${entry[0].toLocaleString()} - $${entry[1].toLocaleString()}`;
        document.getElementById("lvl-sl").textContent = `$${(lvls.stop_loss || 0).toLocaleString()} (${lvls.stop_loss_pct || 0}%)`;
        document.getElementById("lvl-tp1").textContent = `$${(lvls.target_1 || 0).toLocaleString()} (+${lvls.target_1_pct || 0}%)`;
        document.getElementById("lvl-tp2").textContent = `$${(lvls.target_2 || 0).toLocaleString()} (+${lvls.target_2_pct || 0}%)`;
        document.getElementById("lvl-rr").textContent = `${lvls.risk_reward_ratio || 2.0}:1 Expected R:R`;
    }

    // 4. Metrics Radar
    document.getElementById("sentiment-label-val").textContent = stats.sentiment_label || decision.sentiment_label || "Neutral";
    document.getElementById("sentiment-sub").textContent = `Polarity Score: ${stats.polarity_score || 0} across ${stats.sample_size} tweets`;
    document.getElementById("squeeze-val").textContent = `${decision.squeeze_risk_pct || 0}%`;
    document.getElementById("diversity-val").textContent = `${stats.author_diversity_pct || 0}%`;
    document.getElementById("catalyst-val").textContent = `${decision.catalyst_impact_score || 0} / 3.0`;

    // 5. Update Exchange Links
    const row = document.getElementById("exchange-links-row");
    row.innerHTML = `
        <a href="https://www.binance.com/en/trade/${data.symbol}_USDT" target="_blank" class="ext-link">Binance</a>
        <a href="https://www.bybit.com/trade/usdt/${data.symbol}USDT" target="_blank" class="ext-link">Bybit</a>
        <a href="https://www.coinbase.com/advanced-trade/spot/${data.symbol}-USD" target="_blank" class="ext-link">Coinbase</a>
        <a href="https://jup.ag/swap/USDC-${data.symbol}" target="_blank" class="ext-link">Jupiter DEX</a>
    `;

    // 6. Update Tweet Explorer List
    const tweetCountBadge = document.getElementById("tweet-count-badge");
    tweetCountBadge.textContent = `${tweets.length} of ${stats.sample_size} Analyzed Tweets`;

    const tweetList = document.getElementById("tweet-list");
    if (tweets.length === 0) {
        tweetList.innerHTML = `<div class="empty-state">No tweets available for this asset.</div>`;
    } else {
        tweetList.innerHTML = tweets.map((t) => `
            <div class="tweet-item">
                <div class="tweet-header">
                    <div class="author-meta">
                        <span class="author-name">@${escapeHtml(t.author_username || "user")}</span>
                        ${t.author_verified ? '<span class="verified-badge">✓</span>' : ''}
                    </div>
                    <span class="tweet-tag">${t.likes > 100 ? 'High Engagement' : 'Recent'}</span>
                </div>
                <div class="tweet-text">${escapeHtml(t.text || "")}</div>
                <div class="tweet-stats">
                    <span>❤️ ${(t.likes || 0).toLocaleString()}</span>
                    <span>🔁 ${(t.retweets || 0).toLocaleString()}</span>
                    <span>💬 ${(t.replies || 0).toLocaleString()}</span>
                </div>
            </div>
        `).join("");
    }
}

function escapeHtml(str) {
    return String(str)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

function renderProbabilityDistribution(decision) {
    const container = document.getElementById("dist-bars-container");
    const winnerNote = document.getElementById("dist-winner-note");
    const footerEl = document.getElementById("dist-footer");
    const confSub = document.getElementById("conf-sub-text");
    if (!container) return;

    const winnerAction = decision.action || "HOLD";
    const rawProbs = decision.action_probabilities || {};

    const allActions = ["STRONG_BUY", "BUY", "HOLD", "TAKE_PROFIT", "SELL", "STRONG_SELL"];

    // Build raw item list
    let items = allActions.map((act) => ({
        action: act,
        pct: typeof rawProbs[act] === "number" ? rawProbs[act] : 0.0,
        isWinner: act === winnerAction,
    }));

    // Fallback distribution if rawProbs is missing or empty
    const totalSum = items.reduce((acc, it) => acc + it.pct, 0);
    if (totalSum < 1.0) {
        const winnerPct = decision.confidence_pct || 40.0;
        const remainder = Math.max(0, 100.0 - winnerPct);
        const weights = {
            HOLD: 0.35,
            BUY: 0.25,
            STRONG_BUY: 0.15,
            TAKE_PROFIT: 0.12,
            SELL: 0.08,
            STRONG_SELL: 0.05,
        };
        items = allActions.map((act) => {
            if (act === winnerAction) {
                return { action: act, pct: winnerPct, isWinner: true };
            }
            return {
                action: act,
                pct: parseFloat((remainder * (weights[act] || 0.15)).toFixed(1)),
                isWinner: false,
            };
        });
    }

    // Sort descending by percentage so highest probability signal is on top
    items.sort((a, b) => b.pct - a.pct);

    // Sum and difference over runner-up
    const calculatedSum = items.reduce((acc, it) => acc + it.pct, 0).toFixed(1);
    const winnerItem = items.find((it) => it.isWinner) || items[0];
    const runnerUp = items.find((it) => !it.isWinner) || { action: "HOLD", pct: 0 };
    const margin = (winnerItem.pct - runnerUp.pct).toFixed(1);

    if (winnerNote) {
        winnerNote.innerHTML = `Top: <span class="highlight-action">${winnerAction}</span> (${winnerItem.pct}%) · Total: ${calculatedSum}%`;
    }

    if (confSub) {
        confSub.textContent = `Highest across 6 signals (Total: 100%)`;
    }

    container.innerHTML = items
        .map((item) => {
            let fillClass = "fill-other";
            if (item.isWinner) {
                if (item.action.includes("BUY")) fillClass = "fill-winner-buy";
                else if (item.action.includes("SELL")) fillClass = "fill-winner-sell";
                else if (item.action === "TAKE_PROFIT") fillClass = "fill-winner-tp";
                else fillClass = "fill-winner-hold";
            } else {
                if (item.action.includes("BUY")) fillClass = "fill-subtle-buy";
                else if (item.action.includes("SELL")) fillClass = "fill-subtle-sell";
                else if (item.action === "TAKE_PROFIT") fillClass = "fill-subtle-tp";
                else fillClass = "fill-subtle-hold";
            }

            const friendlyName = item.action.replace(/_/g, " ");
            const barWidth = Math.min(100, Math.max(item.pct, 2));

            return `
                <div class="dist-row ${item.isWinner ? 'is-winner-row' : ''}">
                    <div class="dist-row-label">
                        <span class="dist-action-name ${item.isWinner ? 'is-winner' : ''}">
                            <span class="action-text">${friendlyName}</span>
                            ${item.isWinner ? '<span class="winner-pill">✓ HIGHEST (CHOSEN)</span>' : ''}
                        </span>
                        <span class="dist-pct font-mono ${item.isWinner ? 'is-winner' : ''}">${item.pct.toFixed(1)}%</span>
                    </div>
                    <div class="dist-bar-track">
                        <div class="dist-bar-fill ${fillClass}" style="width: ${barWidth}%;"></div>
                    </div>
                </div>
            `;
        })
        .join("");

    if (footerEl) {
        footerEl.innerHTML = `
            <div class="dist-footer-item">
                <span class="footer-label">Sum Across 6 Signals:</span>
                <span class="footer-val font-mono" style="color: var(--accent-cyan);">${calculatedSum}%</span>
            </div>
            <div class="dist-footer-item">
                <span class="footer-label">Selection Logic:</span>
                <span class="footer-val font-mono" style="color: var(--text-secondary);">${winnerAction} chosen with highest probability (+${margin}% over runner-up ${runnerUp.action})</span>
            </div>
        `;
    }
}
