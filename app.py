import streamlit as st
import google.generativeai as genai
import pandas as pd
import json
from PIL import Image

# ================= 配置区 =================
st.set_page_config(page_title="MysteryNarrator 2025", layout="wide", page_icon="🍌")

st.markdown("""
<style>
    .stApp { background-color: #050505; color: #e0e0e0; }
    .stButton>button { background-color: #D4AF37; color: black; border: none; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

with st.sidebar:
    st.title("🍌 2025 Core Engine")
    api_key = st.text_input("Gemini API Key", type="password")
    st.info("Target Models:\n- Text: Gemini 3 Pro (Nano Banana)\n- Image: Imagen 4.0")

# ================= 核心逻辑 =================
def analyze_script(script, key):
    genai.configure(api_key=key)
    
    # 【修正】使用 2025 年的标准文本模型：Gemini 3 Pro (Nano Banana)
    # 旧的 1.5-flash 已被淘汰，不要再用了
    target_model = 'gemini-3-pro-preview'
    
    try:
        model = genai.GenerativeModel(target_model)
        
        prompt = f"""
        You are a mystery video director.
        Script: {script}
        Task: Split script into scenes. Write an Image Prompt for Imagen 4.
        Output JSON: [{{"script": "...", "prompt": "..."}}]
        """
        
        response = model.generate_content(prompt)
        text = response.text.replace('```json', '').replace('```', '').strip()
        return json.loads(text)
        
    except Exception as e:
        # 如果 Gemini 3 也报错，那就真的没有任何文本模型可用了
        st.error(f"文本分析失败 ({target_model}): {e}")
        return None

def generate_image(prompt, key):
    genai.configure(api_key=key)
    
    # 【修正】使用你截图里确认存在的 Imagen 4
    # 旧的 imagen-3.0 已被淘汰
    target_model = 'imagen-4.0-generate-001'
    
    try:
        model = genai.GenerativeModel(target_model)
        
        result = model.generate_images(
            prompt=prompt,
            number_of_images=1,
            aspect_ratio="16:9"
        )
        return result.images[0]._pil_image
    except Exception as e:
        # 捕捉具体错误
        return f"Imagen 4 报错: {str(e)}"

# ================= 主界面 =================
st.title("🍌 MysteryNarrator (2025 Edition)")
st.caption("Using Gemini 3 Pro + Imagen 4")

text_input = st.text_area("输入解说词", height=100)

if st.button("🚀 生成分镜与画面"):
    if not api_key:
        st.error("请填入 Key")
    else:
        with st.spinner("🤖 Nano Banana 正在思考..."):
            scenes = analyze_script(text_input, api_key)
            
        if scenes:
            st.success(f"分析完成！正在调用 Imagen 4...")
            
            result_container = st.container()
            
            for i, scene in enumerate(scenes):
                with result_container:
                    c1, c2 = st.columns([1, 2])
                    with c1:
                        st.markdown(f"**#{i+1}**")
                        st.write(scene['script'])
                        st.caption(scene['prompt'])
                    with c2:
                        img_res = generate_image(scene['prompt'], api_key)
                        if isinstance(img_res, str):
                            st.error("❌ 失败")
                            st.code(img_res)
                        else:
                            st.image(img_res)
                st.divider()
