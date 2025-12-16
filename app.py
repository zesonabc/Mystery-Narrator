import streamlit as st
import google.generativeai as genai
import pandas as pd
import json
import re
from PIL import Image
import io

# ==========================================
# 1. 页面配置
# ==========================================
st.set_page_config(
    page_title="MysteryNarrator - Debug Mode",
    page_icon="🛠️",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    .stApp { background-color: #050505; color: #e0e0e0; }
    [data-testid="stSidebar"] { background-color: #0e0e0e; border-right: 1px solid #333; }
    h1, h2, h3 { color: #ff3333 !important; font-family: 'Courier New', monospace; }
    .stTextArea textarea, .stTextInput input { background-color: #1a1a1a; color: #ffffff; border: 1px solid #444; }
    .stButton > button { background-color: #990000; color: white; border: none; font-weight: bold; }
    .stButton > button:hover { background-color: #cc0000; color: white; }
    hr { border-color: #333; }
    .stDataFrame { border: 1px solid #333; }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 2. Sidebar: 设置区
# ==========================================
with st.sidebar:
    st.markdown("## ⚙️ Core Engine")
    api_key = st.text_input("Gemini API Key", type="password")
    
    st.markdown("---")
    st.markdown("### 🕵️ The Host (博主)")
    default_host = "A 30-year-old Asian man, wearing a green cap and brown leather jacket, looking at the viewer, dramatic lighting, mystery atmosphere."
    host_persona = st.text_area("博主形象", value=default_host, height=80)
    
    st.markdown("### 🎨 Style (画风)")
    default_style = "Cinematic, horror movie style, 80s retro film grain, high contrast, dim lighting, photorealistic, 4k."
    visual_style = st.text_area("整体风格", value=default_style, height=80)

# ==========================================
# 3. 核心功能
# ==========================================

def analyze_script(script_text, host_desc, style_desc, api_key):
    """ Step 1: 文本分析 (使用 Gemini 1.5 Pro - 最稳) """
    if not api_key: return None
    try:
        genai.configure(api_key=api_key)
        # 文本模型改回最稳的 Pro，防止 Nano Banana 不支持文本指令
        model = genai.GenerativeModel('gemini-1.5-pro') 

        prompt = f"""
        任务：将悬疑解说文案拆分为分镜，并生成英文绘画提示词。
        输入：
        1. 博主: {host_desc}
        2. 风格: {style_desc}
        3. 文案: {script_text}

        规则：
        1. 按语速切分文案（3-5秒一段）。
        2. 类型分类：
           - "HOST": 分析、提问、对话（生成博主画面）。
           - "SCENE": 描述环境、动作、物体（生成纯场景，无博主）。
        3. Final Prompt: 必须包含"风格"关键词。如果是 HOST，加上博主描述；如果是 SCENE，只描述场景。

        输出格式：纯 JSON 列表 (不要 Markdown)。
        Example: [{{ "time": "3s", "script": "...", "type": "HOST", "final_prompt": "..." }}]
        """

        with st.spinner("🧠 AI 正在分析剧本..."):
            response = model.generate_content(prompt)
            text = response.text.replace('```json', '').replace('```', '').strip()
            data = json.loads(text)
            return pd.DataFrame(data)
    except Exception as e:
        st.error(f"文本分析出错: {e}")
        return None

def generate_real_image(prompt, api_key):
    """ Step 2: 画图 (使用 Imagen 3 标准版) """
    try:
        genai.configure(api_key=api_key)
        
        # === 强制使用标准 Imagen 3 模型 ===
        # 不要用 Nano Banana，那个不稳定
        target_model = 'imagen-3.0-generate-001'
        
        imagen_model = genai.GenerativeModel(target_model)
        
        result = imagen_model.generate_images(
            prompt=prompt,
            number_of_images=1,
            aspect_ratio="16:9",
            safety_filter="block_only_high"
        )
        
        if result.images:
            return result.images[0]._pil_image
        else:
            return None
            
    except Exception as e:
        # === 这里的改动：不再隐藏错误，直接抛出异常内容 ===
        return f"Error: {str(e)}"

# ==========================================
# 4. 主界面 UI
# ==========================================

st.title("🔪 MysteryNarrator (Debug Mode)")
st.caption("Testing Model: imagen-3.0-generate-001")

# --- Step 1 ---
script_input = st.text_area("📝 输入解说文案", height=100, placeholder="男人推开门，地上的血迹已经干了...")

if 'shot_list_df' not in st.session_state:
    st.session_state.shot_list_df = None

# --- Step 2 ---
if st.button("🎬 1. 分析文案 & 生成 Prompt"):
    if api_key and script_input:
        df = analyze_script(script_input, host_persona, visual_style, api_key)
        if df is not None:
            st.session_state.shot_list_df = df
    else:
        st.warning("请输入 API Key 和文案")

# --- Step 3 ---
if st.session_state.shot_list_df is not None:
    st.markdown("### 📋 确认分镜表")
    edited_df = st.data_editor(
        st.session_state.shot_list_df,
        column_config={
            "final_prompt": st.column_config.TextColumn("绘图指令", width="large"),
            "type": st.column_config.SelectboxColumn("类型", width="small"),
        },
        use_container_width=True,
        hide_index=True
    )
    st.session_state.shot_list_df = edited_df

    # --- Step 4 ---
    st.markdown("---")
    st.markdown(f"### 🎨 2. 生成图片")
    
    if st.button("🚀 开始生成所有图片"):
        if not api_key:
            st.error("缺少 API Key")
        else:
            result_container = st.container()
            total = len(edited_df)
            
            for index, row in edited_df.iterrows():
                with result_container:
                    c1, c2 = st.columns([1, 2])
                    with c1:
                        st.markdown(f"**{index+1}/{total}** `[{row['type']}]`")
                        st.caption(f"Prompt: {row['final_prompt'][:40]}...")
                        status = st.empty()
                        status.text("⏳ 请求中...")
                    
                    with c2:
                        # 调用画图
                        result = generate_real_image(row['final_prompt'], api_key)
                        
                        # 判断返回的是图片还是错误文字
                        if isinstance(result, str) and result.startswith("Error"):
                            status.error("❌ 失败")
                            # 把具体的错误原因打印出来！
                            st.code(result, language="text")
                        elif result:
                            st.image(result, use_container_width=True)
                            status.success("✅ 成功")
                        else:
                            status.error("❌ 未知失败")
                
                st.markdown("---")
