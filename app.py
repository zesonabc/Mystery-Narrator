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
    page_title="MysteryNarrator Pro - 自动画图版",
    page_icon="🎨",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 保持你的黑/红/白 悬疑配色
st.markdown("""
<style>
    .stApp { background-color: #050505; color: #e0e0e0; }
    [data-testid="stSidebar"] { background-color: #0e0e0e; border-right: 1px solid #333; }
    h1, h2, h3 { color: #ff3333 !important; font-family: 'Courier New', monospace; }
    .stTextArea textarea, .stTextInput input { background-color: #1a1a1a; color: #ffffff; border: 1px solid #444; }
    .stButton > button { background-color: #990000; color: white; border: none; font-weight: bold; }
    .stButton > button:hover { background-color: #cc0000; color: white; }
    hr { border-color: #333; }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 2. Sidebar: 设置区
# ==========================================
with st.sidebar:
    st.markdown("## ⚙️ Core Engine")
    
    api_key = st.text_input("Gemini API Key", type="password", help="确保你的 API Key 有 Imagen 权限")
    
    st.markdown("---")
    st.markdown("### 🕵️ The Host (博主)")
    default_host = "A 30-year-old Asian man, wearing a green cap and brown leather jacket, looking at the viewer, dramatic lighting."
    host_persona = st.text_area("博主形象", value=default_host, height=80)
    
    st.markdown("### 🎨 Style (画风)")
    default_style = "Cinematic, horror movie style, 80s retro film grain, high contrast, dim lighting, photorealistic, 4k."
    visual_style = st.text_area("整体风格", value=default_style, height=80)

# ==========================================
# 3. 核心功能：分析文案 + 生成图片
# ==========================================

def analyze_script(script_text, host_desc, style_desc, api_key):
    """ Step 1: 文本分析，生成分镜表 """
    if not api_key: return None
    try:
        genai.configure(api_key=api_key)
        # 使用 Flash 模型进行文本分析，速度快
        model = genai.GenerativeModel('gemini-1.5-flash') 

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

        输出格式：纯 JSON 列表。
        Example: [{{ "time": "3s", "script": "...", "type": "HOST", "visual_desc": "...", "final_prompt": "..." }}]
        """

        with st.spinner("🧠 大脑正在思考分镜..."):
            response = model.generate_content(prompt)
            text = response.text.replace('```json', '').replace('```', '')
            data = json.loads(text)
            return pd.DataFrame(data)
    except Exception as e:
        st.error(f"分析失败: {e}")
        return None

def generate_real_image(prompt, api_key):
    """ Step 2: 真实调用 AI 生成图片 (Imagen 3) """
    try:
        genai.configure(api_key=api_key)
        # 这里调用 Google 的绘图模型 'imagen-3.0-generate-001'
        # 注意：如果你的账号没有 Imagen 权限，这里会报错，需要去 Google AI Studio 开通
        imagen_model = genai.GenerativeModel('imagen-3.0-generate-001')
        
        result = imagen_model.generate_images(
            prompt=prompt,
            number_of_images=1,
            aspect_ratio="16:9", # 适合视频的比例
            safety_filter="block_only_high" # 降低安全过滤，防止悬疑画面被拦截
        )
        
        if result.images:
            return result.images[0]._pil_image
        else:
            return None
    except Exception as e:
        st.warning(f"生成图片失败 (可能是API权限或Prompt敏感): {e}")
        # 如果失败，生成一张黑色占位图，防止程序崩溃
        return Image.new('RGB', (800, 450), color = (20, 0, 0))

# ==========================================
# 4. 主界面 UI
# ==========================================

st.title("🔪 MysteryNarrator Pro")
st.caption("AI 自动分镜 + AI 自动画图 (Integration with Imagen 3)")

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
    
    # 让用户可以编辑 Prompt，因为有时候 AI 写的不够好
    edited_df = st.data_editor(
        st.session_state.shot_list_df,
        column_config={
            "final_prompt": st.column_config.TextColumn("绘图指令 (Final Prompt)", width="large"),
            "type": st.column_config.SelectboxColumn("类型", options=["HOST", "SCENE"], width="small"),
        },
        use_container_width=True,
        hide_index=True
    )
    
    st.session_state.shot_list_df = edited_df # 保存修改

    # --- Step 4: 真实生成图片 ---
    st.markdown("---")
    st.markdown("### 🎨 2. 批量生成图片 (Real Generation)")
    
    st.info("💡 下方将调用 Google Imagen 3 模型真实生成图片，请耐心等待。")
    
    if st.button("🚀 开始生成所有图片"):
        if not api_key:
            st.error("缺少 API Key")
        else:
            # 创建一个容器来动态展示结果
            result_container = st.container()
            
            total = len(edited_df)
            progress_bar = st.progress(0)
            
            # 遍历每一行，真的去调用画图 API
            for index, row in edited_df.iterrows():
                with result_container:
                    # 使用列布局：左边文字，右边图片
                    c1, c2 = st.columns([1, 2])
                    
                    with c1:
                        st.markdown(f"**镜头 {index+1}/{total}** `[{row['type']}]`")
                        st.write(f"🗣️: {row['script']}")
                        st.caption(f"Prompt: {row['final_prompt'][:50]}...")
                        status_text = st.empty()
                        status_text.text("⏳ 正在绘画中...")
                    
                    with c2:
                        # === 关键：这里调用真实的生成函数 ===
                        img = generate_real_image(row['final_prompt'], api_key)
                        
                        if img:
                            st.image(img, use_container_width=True)
                            status_text.text("✅ 完成")
                        else:
                            status_text.error("❌ 生成失败")
                
                st.markdown("---")
                progress_bar.progress((index + 1) / total)
            
            st.success("🎉 所有画面生成完毕！右键保存图片即可使用。")