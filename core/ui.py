"""界面样式：自定义 CSS，统一产品视觉。"""

from __future__ import annotations

CSS = """
<style>
:root {
  --ink: #1B2130;
  --sub: #6B7280;
  --line: #E6E8F0;
  --brand: #4F46E5;
  --brand-2: #7C3AED;
  --soft: #F7F8FD;
}

html, body, [class*="css"] {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC",
    "Microsoft YaHei", "Helvetica Neue", sans-serif;
}

.stApp {
  background:
    radial-gradient(1200px 500px at 12% -8%, #EEF0FF 0%, rgba(238, 240, 255, 0) 60%),
    radial-gradient(900px 400px at 95% 0%, #F6EEFF 0%, rgba(246, 238, 255, 0) 55%),
    #FBFBFE;
}

#MainMenu, footer, header[data-testid="stHeader"] { visibility: hidden; height: 0; }
.block-container { padding-top: 1.4rem; padding-bottom: 3rem; max-width: 1240px; }

/* ---------- 顶部品牌区 ---------- */
.hero {
  display: flex; align-items: center; justify-content: space-between;
  gap: 16px; padding: 22px 26px; margin-bottom: 18px;
  border-radius: 20px; color: #fff;
  background: linear-gradient(120deg, #4F46E5 0%, #6D5BF0 45%, #A855F7 100%);
  box-shadow: 0 18px 40px -18px rgba(79, 70, 229, .55);
}
.hero-left { display: flex; align-items: center; gap: 14px; }
.hero-logo {
  width: 46px; height: 46px; border-radius: 14px; flex: none;
  display: flex; align-items: center; justify-content: center;
  background: rgba(255,255,255,.18); border: 1px solid rgba(255,255,255,.28);
  font-size: 22px;
}
.hero-title { font-size: 22px; font-weight: 700; letter-spacing: .5px; line-height: 1.3; }
.hero-sub { font-size: 13px; opacity: .88; margin-top: 4px; }
.hero-tags { display: flex; gap: 8px; flex-wrap: wrap; justify-content: flex-end; }
.hero-tag {
  font-size: 12px; padding: 5px 11px; border-radius: 999px;
  background: rgba(255,255,255,.16); border: 1px solid rgba(255,255,255,.24);
  white-space: nowrap;
}

/* ---------- 卡片 ---------- */
div[data-testid="stVerticalBlockBorderWrapper"] {
  border-radius: 18px !important;
  border: 1px solid var(--line) !important;
  background: #fff !important;
  box-shadow: 0 10px 30px -22px rgba(24, 32, 60, .35);
  overflow: hidden;
}
div[data-testid="stVerticalBlockBorderWrapper"] > div,
div[data-testid="stVerticalBlockBorderWrapper"] > div > div {
  border-radius: 18px !important;
  background: transparent !important;
}
div[data-testid="stVerticalBlockBorderWrapper"] > div { padding: 10px 8px 4px; }

.card-title {
  display: flex; align-items: center; gap: 8px;
  font-size: 15px; font-weight: 700; color: var(--ink);
  margin: 2px 0 10px;
}
.card-title .dot {
  width: 8px; height: 8px; border-radius: 3px;
  background: linear-gradient(135deg, var(--brand), var(--brand-2));
}

/* ---------- 表单元素 ---------- */
div[data-testid="stTextArea"] textarea, div[data-testid="stTextInput"] input {
  border-radius: 12px !important;
  font-size: 14px !important;
  line-height: 1.7 !important;
}
div[data-baseweb="select"] > div { border-radius: 12px !important; }
label, .stSelectbox label, .stTextArea label { font-size: 13px !important; color: var(--sub); }

/* ---------- 按钮 ---------- */
.stButton > button {
  border-radius: 12px; font-weight: 600; font-size: 13px;
  border: 1px solid var(--line); color: var(--ink); background: #fff;
  padding: 0.34rem 0.6rem; transition: all .16s ease;
}
.stButton > button p { white-space: nowrap; font-size: 13px; }
.stButton > button:hover { border-color: #C7C4F5; color: var(--brand); background: #FAFAFF; }
.stButton > button[kind="primary"] {
  background: linear-gradient(120deg, #4F46E5, #7C3AED);
  border: none; color: #fff;
  box-shadow: 0 12px 24px -14px rgba(79, 70, 229, .8);
}
.stButton > button[kind="primary"]:hover { filter: brightness(1.06); color: #fff; }
.stDownloadButton > button { border-radius: 12px; font-size: 13px; }

/* ---------- 报告正文 ---------- */
[data-testid="stMarkdownContainer"] h1 {
  font-size: 20px; margin: 4px 0 14px; padding-bottom: 10px;
  border-bottom: 1px solid var(--line); color: var(--ink);
}
[data-testid="stMarkdownContainer"] h3 {
  font-size: 15.5px; margin: 20px 0 8px; color: #2B2F45;
  padding-left: 10px; border-left: 3px solid var(--brand);
}
[data-testid="stMarkdownContainer"] ul { padding-left: 20px; }
[data-testid="stMarkdownContainer"] li { margin-bottom: 6px; line-height: 1.85; }
[data-testid="stMarkdownContainer"] p { line-height: 1.8; }
[data-testid="stMarkdownContainer"] strong { color: #3B2FB5; }

/* ---------- 售卖区 ---------- */
.sec-title { font-size: 18px; font-weight: 700; color: var(--ink); margin: 8px 0 12px; }
.step {
  display: flex; align-items: flex-start; gap: 10px; padding: 12px 14px;
  border-radius: 14px; background: #fff; border: 1px solid var(--line); height: 100%;
}
.step-num {
  flex: none; width: 24px; height: 24px; border-radius: 8px; font-size: 13px; font-weight: 700;
  display: flex; align-items: center; justify-content: center; color: #fff;
  background: linear-gradient(135deg, var(--brand), var(--brand-2));
}
.step-title { font-size: 13.5px; font-weight: 600; color: var(--ink); }
.step-desc { font-size: 11.5px; color: var(--sub); line-height: 1.55; margin-top: 2px; }

.plan-card { text-align: center; padding: 2px 0 8px; position: relative; }
.plan-badge {
  display: inline-block; font-size: 10.5px; color: #fff; padding: 2px 8px; border-radius: 999px;
  background: linear-gradient(120deg, #4F46E5, #A855F7); margin-bottom: 4px;
}
.plan-name { font-size: 13.5px; font-weight: 600; color: var(--ink); }
.plan-price { font-size: 25px; font-weight: 700; color: var(--brand); line-height: 1.45; }
.plan-price .rmb { font-size: 14px; font-weight: 600; margin-right: 1px; }
.plan-uses { font-size: 12.5px; color: var(--ink); }
.plan-desc { font-size: 11px; color: var(--sub); line-height: 1.5; margin-top: 4px; min-height: 30px; }

/* ---------- 手机端适配 ---------- */
@media (max-width: 1150px) {
  .st-key-plan_row div[data-testid="stHorizontalBlock"] { flex-wrap: wrap !important; row-gap: 10px !important; }
  .st-key-plan_row div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"] {
    min-width: calc(50% - 6px) !important; flex: 1 1 calc(50% - 6px) !important; width: auto !important;
  }
}
@media (max-width: 760px) {
  .block-container { padding: 0.8rem 0.7rem 2rem !important; }
  .hero { flex-direction: column; align-items: flex-start; padding: 18px; border-radius: 16px; }
  .hero-title { font-size: 19px; }
  .hero-tags { justify-content: flex-start; margin-top: 10px; }
  .hero-tag { font-size: 11px; padding: 4px 9px; }
  div[data-testid="stHorizontalBlock"] { flex-wrap: wrap !important; }
  div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"] {
    min-width: 100% !important; flex: 1 1 100% !important; width: 100% !important;
  }
  .plan-desc { min-height: auto; }
  div[data-testid="stVerticalBlockBorderWrapper"] > div { padding: 8px 4px 2px; }
}
.pill {
  display: inline-block; font-size: 12px; color: var(--brand);
  background: #F2F0FF; border: 1px solid #E1DCFF;
  padding: 3px 10px; border-radius: 999px; margin-right: 6px;
}
.muted { color: var(--sub); font-size: 13px; line-height: 1.7; }
.quota {
  padding: 12px 14px; border-radius: 14px; margin-bottom: 6px;
  background: linear-gradient(120deg, #F4F2FF, #FBF7FF);
  border: 1px solid #E6E1FF;
}
.quota b { font-size: 26px; color: var(--brand); line-height: 1.2; }
.quota-unit { font-size: 13px; color: var(--sub); margin-left: 4px; }
.quota-sub { font-size: 12px; color: var(--sub); margin-top: 2px; }
.empty {
  text-align: center; color: var(--sub); font-size: 13.5px;
  padding: 46px 18px; line-height: 2;
}
.empty .big { font-size: 34px; display: block; margin-bottom: 6px; }
div[data-testid="stExpander"] { border-radius: 14px; }
section[data-testid="stSidebar"] { background: #FFFFFF; border-right: 1px solid var(--line); }
hr { border-color: var(--line); }
</style>
"""
