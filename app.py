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
    .stButton>button { background-color: #00CC66; color: white; border: none; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

with st.sidebar:
    st.title("🍌 2025 Engine")
    api_key = st.text_input("Gemini API Key", type="password")
    st.success("Targeting Free Models:\n1. Nano Banana (2.5 Flash Image)\n2. Imagen 4 Fast")

# ================= 核心逻辑 =================
def analyze_script(script, key):
    genai.configure(api_key=key)
    
    # 1. 文本模型：使用 Gemini 2.5 Flash
    # (截图里显示的最新 Flash 模型，通常免费)
    target_model = 'gemini-2.5-flash'
    
    try:
        model = genai.GenerativeModel(target_model)
        
        prompt = f"""
        You are a mystery video director.
        Script: {script}
        Task: Split script into scenes. Write an Image Prompt.
        Output JSON: [{{"script": "...", "prompt": "..."}}]
        """
        
        response = model.generate_content(prompt)
        text = response.text.replace('```json', '').replace('```', '').strip()
        return json.loads(text)
        
    except Exception as e:
        st.error(f"文本分析失败 ({target_model}): {e}")
        return None

def generate_image(prompt, key):
    genai.configure(api_key=key)
    
    # === 关键修改：双保险画图 ===
    
    # 优先尝试：Nano Banana (你刚才说能生成的那个)
    # ID: gemini-2.5-flash-image
    model_priority_1 = 'gemini-2.5-flash-image'
    
    # 备选尝试：Imagen 4 Fast (通常是免费版专用)
    # ID: imagen-4.0-fast-generate-001
    model_priority_2 = 'imagen-4.0-fast-generate-001'
    
    try:
        # 试第一种
        model = genai.GenerativeModel(model_priority_1)
        result = model.generate_images(prompt=prompt, number_of_images=1, aspect_ratio="16:9")
        return result.images[0]._pil_image
    except Exception as e1:
        # 第一种失败了，静默尝试第二种
        try:
            print(f"Nano Banana 失败，尝试 Imagen 4 Fast... {e1}")
            model = genai.GenerativeModel(model_priority_2)
            result = model.generate_images(prompt=prompt, number_of_images=1, aspect_ratio="16:9")
            return result.images[0]._pil_image
        except Exception as e2:
            return f"所有免费模型均失败。\nNano Banana: {e1}\nImagen 4 Fast: {e2}"

# ================= 主界面 =================
st.title("🍌 MysteryNarrator (Final Free Edition)")
st.caption("Auto-switching: Nano Banana -> Imagen 4 Fast")

text_input = st.text_area("输入解说词", height=100)

if st.button("🚀 生成"):
    if not api_key:
        st.error("请填入 Key")
    else:
        with st.spinner("🤖 正在分析文案..."):
            scenes = analyze_script(text_input, api_key)
            
        if scenes:
            st.success(f"分析完成！开始画图...")
            
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
                            st.warning("⚠️ 画图失败")
                            # 只显示最后 100 个字符的报错，防止刷屏
                            st.caption(img_res[-200:])
                        else:
                            st.image(img_res)
                st.divider()
