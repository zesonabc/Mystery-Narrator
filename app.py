import streamlit as st
import google.generativeai as genai
import pandas as pd
import json
from PIL import Image

# ================= 配置区 =================
st.set_page_config(page_title="MysteryNarrator Final", layout="wide", page_icon="🍌")

st.markdown("""
<style>
    .stApp { background-color: #050505; color: #e0e0e0; }
    .stButton>button { background-color: #00CC66; color: white; border: none; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

with st.sidebar:
    st.title("🍌 Engine Status")
    
    # === 版本检测 (关键) ===
    current_ver = genai.__version__
    st.write(f"SDK Version: `{current_ver}`")
    
    if current_ver < "0.8.3":
        st.error("❌ 版本过低！")
        st.warning("请去修改 requirements.txt 为 google-generativeai>=0.8.3 并重启 App！")
    else:
        st.success("✅ 版本正常 (支持画图)")
        
    api_key = st.text_input("Gemini API Key", type="password")

# ================= 核心逻辑 =================
def analyze_script(script, key):
    genai.configure(api_key=key)
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
    
    # 优先尝试你成功的 Nano Banana
    model_name = 'gemini-2.5-flash-image'
    
    try:
        model = genai.GenerativeModel(model_name)
        
        # 这里的 generate_images 函数只有在 SDK >= 0.8.3 才存在
        result = model.generate_images(
            prompt=prompt,
            number_of_images=1,
            aspect_ratio="16:9"
        )
        return result.images[0]._pil_image
    except Exception as e:
        # 如果失败，尝试 Imagen 4 Fast
        try:
            fallback = 'imagen-4.0-fast-generate-001'
            model = genai.GenerativeModel(fallback)
            result = model.generate_images(prompt=prompt, number_of_images=1)
            return result.images[0]._pil_image
        except Exception as e2:
            return f"画图报错: {e}"

# ================= 主界面 =================
st.title("🍌 MysteryNarrator (Ready)")

text_input = st.text_area("输入解说词", height=100)

if st.button("🚀 生成"):
    if not api_key:
        st.error("请填入 Key")
    else:
        # 再次检查版本，防止白跑
        if genai.__version__ < "0.8.3":
            st.error(f"严重错误：服务器软件版本太老 ({genai.__version__})。请更新 requirements.txt 并重启 App。")
            st.stop()

        with st.spinner("🤖 正在分析..."):
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
                    with c2:
                        img_res = generate_image(scene['prompt'], api_key)
                        if isinstance(img_res, str):
                            st.warning("⚠️ 画图失败")
                            st.caption(img_res[-100:])
                        else:
                            st.image(img_res)
                st.divider()
