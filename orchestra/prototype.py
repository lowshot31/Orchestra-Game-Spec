from __future__ import annotations

import json
import logging
import os
import re
import urllib.error
import urllib.request
from collections.abc import Mapping
from pathlib import Path

LOGGER = logging.getLogger(__name__)


def generate_playable_prototype(
    idea: str,
    final_spec: str,
    artifact_dir: Path | str,
    run_name: str,
    env: Mapping[str, str] | None = None,
) -> Path:
    source = dict(os.environ if env is None else env)
    artifact_path = Path(artifact_dir)
    if source.get("DISCORD_PROJECT") or source.get("CLI_RUN"):
        playable_dir = artifact_path / "game"
    else:
        playable_dir = artifact_path / "playable" / _safe_dirname(run_name)
    playable_dir.mkdir(parents=True, exist_ok=True)

    bundle = _build_mock_bundle(idea, final_spec)
    used_fallback = False
    if source.get("AGENT_MODE", "mock").strip().lower() in {"ollama", "api"}:
        try:
            bundle = _generate_with_ollama(idea, final_spec, source)
        except RuntimeError as exc:
            LOGGER.warning("Ollama prototype generation failed, using mock fallback: %s", exc)
            bundle = _build_mock_bundle(idea, final_spec)
            used_fallback = True
    if used_fallback:
        LOGGER.info("Prototype used mock fallback for idea: %s", idea[:60])

    (playable_dir / "index.html").write_text(bundle["index.html"], encoding="utf-8")
    (playable_dir / "style.css").write_text(bundle["style.css"], encoding="utf-8")
    (playable_dir / "game.js").write_text(bundle["game.js"], encoding="utf-8")
    return playable_dir


def _generate_with_ollama(
    idea: str,
    final_spec: str,
    env: Mapping[str, str],
) -> dict[str, str]:
    model = env.get("PROTOTYPE_MODEL") or env.get("DESIGNER_MODEL") or "qwen2.5-coder:7b-instruct"
    base_url = env.get("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")

    # HTML/CSS는 템플릿 사용, Ollama는 game.js만 생성
    mock = _build_mock_bundle(idea, final_spec)
    game_js = _generate_game_js_with_ollama(idea, final_spec, model, base_url)
    if game_js:
        mock["game.js"] = game_js
        LOGGER.info("Ollama generated game.js successfully (%d chars)", len(game_js))
    else:
        LOGGER.warning("Ollama game.js generation failed, using mock game.js")
    return mock


def _generate_game_js_with_ollama(
    idea: str,
    final_spec: str,
    model: str,
    base_url: str,
) -> str | None:
    """Ollama에게 game.js만 생성하게 한다. HTML/CSS는 템플릿."""
    prompt = (
        "Write ONLY JavaScript code for a browser game. No explanation, no markdown, just code.\n\n"
        "The HTML page already has these elements:\n"
        '- <strong id="score">0</strong> — score display\n'
        '- <strong id="time">60</strong> — timer display\n'
        '- <strong id="best">0</strong> — best score display\n'
        '- <button id="startButton">Start Run</button> — start button\n'
        '- <div id="lane" class="lane"></div> — 420px tall game area\n'
        '- <p id="specNote"></p> — notes area\n\n'
        f"Game idea: {idea}\n\n"
        "Requirements:\n"
        "- Use getElementById to get elements above\n"
        "- 60 second countdown timer\n"
        "- Score tracking with best score in localStorage\n"
        "- startButton click starts the game\n"
        "- Create interactive elements inside the #lane div\n"
        "- Mobile friendly (touch/click events)\n"
        "- Keep it under 80 lines\n"
    )
    payload = json.dumps(
        {"model": model, "prompt": prompt, "stream": False}
    ).encode("utf-8")
    request = urllib.request.Request(
        f"{base_url}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            data = json.loads(response.read().decode("utf-8"))
            raw = data.get("response", "").strip()
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        LOGGER.warning("Ollama JS generation request failed: %s", exc)
        return None

    # 마크다운 코드블록 제거
    code = raw
    if "```" in code:
        parts = code.split("```")
        for part in parts:
            stripped = part.strip()
            if stripped.startswith("javascript") or stripped.startswith("js"):
                code = stripped.split("\n", 1)[-1] if "\n" in stripped else stripped
                break
            elif "getElementById" in stripped or "addEventListener" in stripped:
                code = stripped
                break

    # 최소 검증: getElementById가 있어야 유효한 게임 코드
    if "getElementById" not in code or len(code) < 100:
        LOGGER.warning("Ollama JS output too short or invalid (%d chars)", len(code))
        return None

    return code


def _build_mock_bundle(idea: str, final_spec: str) -> dict[str, str]:
    title = _derive_title(idea)
    summary = _escape_js(idea)
    spec_note = _escape_js(_compact_spec(final_spec))
    index_html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <link rel="stylesheet" href="style.css">
</head>
<body>
  <main class="game-shell">
    <header class="game-header">
      <p class="eyebrow">Orchestra Playable Prototype</p>
      <h1>{title}</h1>
      <p class="summary">{idea}</p>
    </header>
    <section class="hud">
      <div><span>Score</span><strong id="score">0</strong></div>
      <div><span>Time</span><strong id="time">60</strong></div>
      <div><span>Best</span><strong id="best">0</strong></div>
    </section>
    <section class="board">
      <button id="startButton" class="primary">Start Run</button>
      <div id="lane" class="lane" aria-live="polite"></div>
    </section>
    <section class="notes">
      <h2>Run Notes</h2>
      <p id="specNote">{spec_note}</p>
      <p class="hint">Tap the glowing beats before they cross the hit line. Miss too many and the minute slips away.</p>
    </section>
  </main>
  <script src="game.js"></script>
</body>
</html>
"""
    style_css = """:root {
  --bg: #0f1117;
  --panel: #171b25;
  --panel-edge: #2b3140;
  --text: #f5f7fb;
  --muted: #a6afc3;
  --accent: #ff6f61;
  --accent-2: #ffd166;
  --ok: #56d364;
}

* { box-sizing: border-box; }
body {
  margin: 0;
  min-height: 100vh;
  font-family: "Trebuchet MS", "Segoe UI", sans-serif;
  color: var(--text);
  background:
    radial-gradient(circle at top, rgba(255,111,97,0.18), transparent 30%),
    linear-gradient(180deg, #0b0d13 0%, var(--bg) 100%);
}

.game-shell {
  width: min(920px, calc(100vw - 32px));
  margin: 0 auto;
  padding: 28px 0 40px;
}

.game-header h1 {
  margin: 8px 0 12px;
  font-size: clamp(2rem, 5vw, 3.4rem);
}

.eyebrow, .summary, .hint, .notes p, .hud span {
  color: var(--muted);
}

.hud {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  margin: 18px 0;
}

.hud div, .notes, .board {
  background: rgba(23, 27, 37, 0.92);
  border: 1px solid var(--panel-edge);
  border-radius: 8px;
}

.hud div {
  padding: 14px 16px;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.hud strong {
  font-size: 1.3rem;
}

.board {
  position: relative;
  padding: 16px;
}

.primary {
  appearance: none;
  border: 0;
  border-radius: 8px;
  background: linear-gradient(135deg, var(--accent), var(--accent-2));
  color: #1b120d;
  font-weight: 700;
  padding: 12px 18px;
  cursor: pointer;
  margin-bottom: 14px;
}

.lane {
  position: relative;
  height: 420px;
  border-radius: 8px;
  overflow: hidden;
  background:
    linear-gradient(180deg, rgba(255,255,255,0.06), transparent 18%),
    linear-gradient(180deg, rgba(255,255,255,0.02), rgba(255,255,255,0.01));
}

.lane::after {
  content: "";
  position: absolute;
  left: 10%;
  right: 10%;
  bottom: 54px;
  height: 4px;
  border-radius: 999px;
  background: rgba(255, 209, 102, 0.8);
  box-shadow: 0 0 18px rgba(255, 209, 102, 0.45);
}

.beat {
  position: absolute;
  left: 50%;
  width: 72px;
  height: 72px;
  margin-left: -36px;
  border: 0;
  border-radius: 50%;
  background: radial-gradient(circle at 30% 30%, #fff3d6 0%, #ffd166 35%, #ff6f61 100%);
  color: #24160e;
  font-weight: 700;
  cursor: pointer;
  box-shadow: 0 14px 28px rgba(0, 0, 0, 0.35);
}

.notes {
  margin-top: 18px;
  padding: 16px;
}

@media (max-width: 640px) {
  .game-shell { width: calc(100vw - 20px); }
  .hud { grid-template-columns: 1fr; }
  .lane { height: 360px; }
}

/* Ollama가 생성하는 모든 게임 요소에 기본 스타일 적용 */
.lane > * {
  position: absolute;
  min-width: 40px;
  min-height: 40px;
  padding: 6px 10px;
  border-radius: 12px;
  background: linear-gradient(135deg, var(--accent), var(--accent-2));
  color: #1b120d;
  font-weight: 700;
  font-size: 1rem;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  box-shadow: 0 6px 18px rgba(0,0,0,0.3);
  transition: transform 0.12s, opacity 0.15s;
  user-select: none;
  border: none;
}

.lane > *:hover {
  transform: scale(1.15);
  filter: brightness(1.1);
}

.lane > *:active {
  transform: scale(0.85);
  opacity: 0.7;
}

@keyframes pulse {
  0%, 100% { transform: scale(1); }
  50% { transform: scale(1.1); }
}

@keyframes fall {
  from { top: -60px; }
  to { top: 420px; }
}
"""
    game_js = f"""const scoreEl = document.getElementById("score");
const timeEl = document.getElementById("time");
const bestEl = document.getElementById("best");
const laneEl = document.getElementById("lane");
const startButton = document.getElementById("startButton");

const gameState = {{
  running: false,
  score: 0,
  timeLeft: 60,
  best: 0,
  beatTimer: null,
  clockTimer: null,
  prompt: "{summary}",
}};

function updateHud() {{
  scoreEl.textContent = String(gameState.score);
  timeEl.textContent = String(gameState.timeLeft);
  bestEl.textContent = String(gameState.best);
}}

function resetGame() {{
  laneEl.querySelectorAll(".beat").forEach((node) => node.remove());
  gameState.score = 0;
  gameState.timeLeft = 60;
  updateHud();
}}

function stopGame() {{
  gameState.running = false;
  clearInterval(gameState.beatTimer);
  clearInterval(gameState.clockTimer);
  startButton.disabled = false;
  startButton.textContent = "Play Again";
  if (gameState.score > gameState.best) {{
    gameState.best = gameState.score;
    updateHud();
  }}
}}

function missBeat(node) {{
  if (!gameState.running) return;
  node.remove();
  gameState.score = Math.max(0, gameState.score - 1);
  updateHud();
}}

function spawnBeat() {{
  if (!gameState.running) return;
  const beat = document.createElement("button");
  beat.className = "beat";
  beat.type = "button";
  beat.textContent = "TAP";
  const drift = Math.floor(Math.random() * 40) - 20;
  beat.style.left = `calc(50% + ${{drift}}%)`;
  beat.style.top = "-72px";
  laneEl.appendChild(beat);

  let top = -72;
  const speed = 2.8 + Math.random() * 1.4;
  const animation = window.setInterval(() => {{
    top += speed;
    beat.style.top = `${{top}}px`;
    if (top > laneEl.clientHeight - 40) {{
      clearInterval(animation);
      missBeat(beat);
    }}
  }}, 16);

  beat.addEventListener("click", () => {{
    if (!gameState.running) return;
    clearInterval(animation);
    beat.remove();
    gameState.score += 3;
    updateHud();
  }});
}}

function startGame() {{
  resetGame();
  gameState.running = true;
  startButton.disabled = true;
  startButton.textContent = "Running";
  gameState.beatTimer = window.setInterval(spawnBeat, 850);
  gameState.clockTimer = window.setInterval(() => {{
    gameState.timeLeft -= 1;
    updateHud();
    if (gameState.timeLeft <= 0) {{
      stopGame();
    }}
  }}, 1000);
  spawnBeat();
}}

document.getElementById("specNote").textContent = `{spec_note}`;
startButton.addEventListener("click", startGame);
updateHud();
"""
    return {
        "index.html": index_html,
        "style.css": style_css,
        "game.js": game_js,
    }


def _derive_title(idea: str) -> str:
    stripped = re.sub(r"\s+", " ", idea.strip())
    if not stripped:
        return "Orchestra Mini Game"
    return stripped[:48]


def _compact_spec(final_spec: str) -> str:
    lines = [line.strip("- ").strip() for line in final_spec.splitlines() if line.strip()]
    return " ".join(lines[:6])


def _safe_dirname(value: str) -> str:
    cleaned = re.sub(r"[^0-9A-Za-z가-힣._-]+", "-", value.strip())
    return cleaned.strip("-") or "latest"


def _escape_js(value: str) -> str:
    return value.replace("\\", "\\\\").replace("`", "\\`").replace("${", "\\${")
