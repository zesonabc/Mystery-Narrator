import streamlit as st
import google.generativeai as genai
import pandas as pd
import json
import re
from PIL import Image
import io

# ==========================================
# 1. 页面配置 (保持不变)
# ==========================================
st.set_page_config(
    page_title="MysteryNarrator - Gemini 3 Edition",
    page_icon="🍌",
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
    st.markdown("## ⚙️ Core Engine (Gemini 3)")
    
    api_key = st.text_input("Gemini API Key", type="password")
    
    st.markdown("---")
    st.markdown("### 🕵️ The Host (博主)")
    default_host = "A 30-year-old Asian man, wearing a green cap and brown leather jacket, looking at the viewer, dramatic lighting, mystery atmosphere."
    host_persona = st.text_area("博主形象", value=default_host, height=80)
    
    st.markdown("### 🎨 Style (画风)")
    default_style = "Cinematic, horror movie style, 80s retro film grain, high contrast, dim lighting, photorealistic, 4k."
    visual_style = st.text_area("整体风格", value=default_style, height=80)

# ==========================================
# 3. 核心功能：适配你的 Nano Banana Pro 模型
# ==========================================

def analyze_script(script_text, host_desc, style_desc, api_key):
    """ Step 1: 文本分析 (使用 Gemini 3 Pro Preview) """
    if not api_key: return None

    try:
        genai.configure(api_key=api_key)
        
        # 1. 这里改成你上一个截图里的文本模型 ID
        # 如果报错，说明你的账号只能用 image 模型，那就把这里改回 'gemini-1.5-pro'
        model_id = 'gemini-3-pro-preview' 
        
        model = genai.GenerativeModel(model_id) 

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

        with st.spinner(f"🧠 AI ({model_id}) 正在分析剧本..."):
            response = model.generate_content(prompt)
            text = response.text.replace('```json', '').replace('```', '').strip()
            data = json.loads(text)
            return pd.DataFrame(data)
            
    except Exception as e:
        st.error(f"文本分析失败: {e}")
        st.warning("提示：如果文本模型报错，请检查你的 API Key 是否支持 'gemini-3-pro-preview'，或者尝试换回 'gemini-1.5-pro'。")
        return None

def generate_real_image(prompt, api_key):
    """ Step 2: 画图 (使用 Gemini 3 Pro Image Preview / Nano Banana Pro) """
    try:
        genai.configure(api_key=api_key)
        
        # === 关键修改：这里填你截图里那个“香蕉”模型的 ID ===
        target_image_model = 'gemini-3-pro-image-preview'
        
        imagen_model = genai.GenerativeModel(target_image_model)
        
        # 注意：Gemini 3 Image 模型的参数可能略有不同
        # 这里使用通用的生成方法
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
        print(f"画图详细报错: {e}")
        return None

# ==========================================
# 4. 主界面 UI
# ==========================================

st.title("🍌 MysteryNarrator (Banana Edition)")
st.caption("Current Model: Gemini 3 Pro Preview")

# --- Step 1: 输入文案 ---
script_input = st.text_area("📝 输入解说文案", height=100, placeholder="男人推开门，地上的血迹已经干了...")

if 'shot_list_df' not in st.session_state:
    st.session_state.shot_list_df = None

# --- Step 2: 生成分镜表 ---
if st.button("🎬 1. 分析文案 & 生成 Prompt"):
    if api_key and script_input:
        df = analyze_script(script_input, host_persona, visual_style, api_key)
        if df is not None:
            st.session_state.shot_list_df = df
    else:
        st.warning("请输入 API Key 和文案")

# --- Step 3: 展示表格并允许微调 ---
if st.session_state.shot_list_df is not None:
    st.markdown("### 📋 确认分镜表")
    
    edited_df = st.data_editor(
        st.session_state.shot_list_df,
        column_config={
            "final_prompt": st.column_config.TextColumn("绘图指令", width="large"),
            "type": st.column_config.SelectboxColumn("类型", options=["HOST", "SCENE"], width="small"),
        },
        use_container_width=True,
        hide_index=True
    )
    
    st.session_state.shot_list_df = edited_df

    # --- Step 4: 真实生成图片 ---
    st.markdown("---")
    st.markdown(f"### 🎨 2. 生成图片 (Using: gemini-3-pro-image-preview)")
    
    if st.button("🚀 开始生成所有图片"):
        if not api_key:
            st.error("缺少 API Key")
        else:
            result_container = st.container()
            total = len(edited_df)
            progress_bar = st.progress(0)
            
            for index, row in edited_df.iterrows():
                with result_container:
                    c1, c2 = st.columns([1, 2])
                    
                    with c1:
                        st.markdown(f"**{index+1}/{total}** `[{row['type']}]`")
                        st.caption(f"Prompt: {row['final_prompt'][:40]}...")
                        status_text = st.empty()
                        status_text.text("⏳ 正在请求 Nano Banana...")
                    
                    with c2:
                        img = generate_real_image(row['final_prompt'], api_key)
                        if img:
                            st.image(img, use_container_width=True)
                            status_text.success("✅ Success")
                        else:
                            # 失败时显示更详细的提示
                            status_text.error("❌ Failed")
                            st.warning("生成失败。请检查：1.Prompt是否包含敏感词 2.API Key 权限")
                
                st.markdown("---")
                progress_bar.progress((index + 1) / total)
            
            st.success("🎉 流程结束")
