import streamlit as st
import google.generativeai as genai
import pandas as pd

st.set_page_config(page_title="API 体检中心", layout="wide", page_icon="🏥")

st.title("🏥 Gemini API 深度体检")
st.markdown("不要慌，我们一个个测试，看看到底是哪个环节报错。")

api_key = st.text_input("请输入刚才新建的 API Key", type="password")

if st.button("🚀 开始体检"):
    if not api_key:
        st.error("请填入 Key")
    else:
        genai.configure(api_key=api_key)
        
        # 我们测试这 4 个最常用的标准模型
        # 这些是 Google 官方文档里最稳的，绝对不是 Nano Banana 那种实验品
        test_models = [
            "gemini-1.5-flash", 
            "gemini-1.5-flash-8b",
            "gemini-1.5-pro",
            "gemini-1.0-pro"
        ]
        
        results = []
        
        progress_bar = st.progress(0)
        
        for i, model_name in enumerate(test_models):
            status = "未知"
            detail = ""
            
            try:
                # 尝试连接
                model = genai.GenerativeModel(model_name)
                # 发送极简请求
                response = model.generate_content("Test", request_options={"timeout": 10})
                
                # 如果能走到这一步，说明成功了！
                status = "✅ 通畅"
                detail = "连接成功，可以使用！"
                
            except Exception as e:
                # 捕捉具体的报错信息
                error_str = str(e)
                status = "❌ 失败"
                
                if "404" in error_str:
                    detail = "404 Not Found (模型不存在/不支持)"
                elif "429" in error_str:
                    detail = "429 Quota Exceeded (免费额度耗尽/需付费)"
                elif "403" in error_str:
                    detail = "403 Permission Denied (API Key 权限不足/地区限制)"
                elif "API key not valid" in error_str:
                    detail = "Key 无效 (复制错了吗？)"
                else:
                    # 打印原始错误的前100个字符
                    detail = f"其他错误: {error_str[:150]}..."
            
            results.append({
                "模型名称": model_name,
                "状态": status,
                "详细诊断": detail
            })
            progress_bar.progress((i + 1) / len(test_models))

        # 展示体检报告
        st.markdown("### 📋 体检报告")
        df = pd.DataFrame(results)
        st.table(df)
        
        # 智能建议
        st.markdown("### 💡 医生建议")
        success_count = len([r for r in results if r['状态'] == "✅ 通畅"])
        
        if success_count > 0:
            st.success(f"好消息！发现了 {success_count} 个可用的模型。")
            working_model = [r['模型名称'] for r in results if r['状态'] == "✅ 通畅"][0]
            st.write(f"👉 请把你之后代码里的模型名字改成： **`{working_model}`** 即可解决问题！")
        else:
            st.error("所有模型都无法连接。")
            st.write("可能原因：")
            st.write("1. 你的 Google Cloud Project 没有开启 Generative Language API。")
            st.write("2. 这个 Key 是新建的，可能需要等 1-2 分钟生效。")
            st.write("3. Streamlit 服务器的网络暂时连不上 Google。")
