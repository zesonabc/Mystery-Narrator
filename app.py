import streamlit as st
import google.generativeai as genai
import pandas as pd
import json
import re
from PIL import Image
import io

# ==========================================
# 1. 页面配置与悬疑风格 CSS
# ==========================================
st.set_page_config(
    page_title="MysteryNarrator Ultimate",
    page_icon="🕵️‍♂️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 强制黑/红/白 悬疑配色
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
    
    api_key = st.text_input("Gemini API Key", type="password", help="输入你的 Google API Key (需开通 Gemini 和 Imagen)")
    
    st.markdown("---")
    st.markdown("### 🕵️ The Host (博主)")
    default_host = "A 30-year-old Asian man, wearing a green cap and brown leather jacket, looking at the viewer, dramatic lighting, mystery atmosphere."
    host_persona = st.text_area("博主形象", value=default_host, height=80)
    
    st.markdown("### 🎨 Style (画风)")
    default_style = "Cinematic, horror movie style, 80s retro film grain, high contrast, dim lighting, photorealistic, 4k."
    visual_style = st.text_area("整体风格", value=default_style, height=80)

# ==========================================
# 3. 核心功能：智能分析 + 自动纠错
# ==========================================

def get_best_available_model(api_key):
    """自动寻找可用的模型，防止 404 错误"""
    try:
        genai.configure(api_key=api_key)
        all_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        
        # 优先级列表：优先用 Flash (快)，其次 Pro (强)，最后保底
        priority_list = [
            'models/gemini-1.5-flash',
            'models/gemini-1.5-pro',
            'models/gemini-pro',
            'models/gemini-1.0-pro'
        ]
        
        for model_name in priority_list:
            if model_name in all_models:
                return model_name
        
        # 如果都在列表里没找到，就返回列表里的第一个能用的
        if all_models:
            return all_models[0]
            
        return None
    except Exception as e:
        st.error(f"连接 Google 服务器失败: {e}")
        return None

def analyze_script(script_text, host_desc, style_desc, api_key):
    """ Step 1: 文本分析，生成分镜表 """
    if not api_key: return None

    # --- 1. 自动寻找模型 ---
    model_name = get_best_available_model(api_key)
    if not model_name:
        st.error("❌ 未找到任何可用的 Gemini 模型，请检查 API Key 或网络。")
        return None
    
    st.toast(f"已连接模型: {model_name.replace('models/', '')}") # 提示用户

    try:
        # --- 2. 开始生成 ---
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(model_name) 

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

        with st.spinner(f"🧠 AI ({model_name.replace('models/', '')}) 正在分析剧本..."):
            response = model.generate_content(prompt)
            # 清理可能存在的 markdown 符号
            text = response.text.replace('```json', '').replace('```', '').strip()
            data = json.loads(text)
            return pd.DataFrame(data)
            
    except Exception as e:
        st.error(f"分析过程中出错: {e}")
        return None

def generate_real_image(prompt, api_key):
    """ Step 2: 真实调用 AI 生成图片 (Imagen 3) """
    try:
        genai.configure(api_key=api_key)
        # Imagen 3 的标准调用名称
        imagen_model = genai.GenerativeModel('imagen-3.0-generate-001')
        
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
        # 如果失败，不中断程序，而是返回 None
        print(f"画图失败: {e}") 
        return None

# ==========================================
# 4. 主界面 UI
# ==========================================

st.title("🔪 MysteryNarrator Pro")
st.caption("自动寻找可用模型 | 智能分镜 | Imagen 3 画图")

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
    st.markdown("### 📋 确认分镜表 (可修改 Prompt)")
    
    # 允许用户编辑 Prompt
    edited_df = st.data_editor(
        st.session_state.shot_list_df,
        column_config={
            "final_prompt": st.column_config.TextColumn("绘图指令 (Final Prompt)", width="large"),
            "type": st.column_config.SelectboxColumn("类型", options=["HOST", "SCENE"], width="small"),
        },
        use_container_width=True,
        hide_index=True
    )
    
    st.session_state.shot_list_df = edited_df

    # --- Step 4: 真实生成图片 ---
    st.markdown("---")
    st.markdown("### 🎨 2. 批量生成图片 (Real Generation)")
    
    st.info("💡 下方将调用 Google Imagen 3 模型。如果报错，说明你的 Key 暂无画图权限。")
    
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
                        st.markdown(f"**镜头 {index+1}/{total}** `[{row['type']}]`")
                        st.write(f"🗣️: {row['script']}")
                        status_text = st.empty()
                        status_text.text("⏳ 正在绘画中...")
                    
                    with c2:
                        img = generate_real_image(row['final_prompt'], api_key)
                        if img:
                            st.image(img, use_container_width=True)
                            status_text.success("✅ 完成")
                        else:
                            st.warning("❌ 生成失败 (可能无 Imagen 权限)")
                            status_text.error("Failed")
                
                st.markdown("---")
                progress_bar.progress((index + 1) / total)
            
            st.success("🎉 流程结束")
