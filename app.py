import streamlit as st
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import google.generativeai as genai
import json
import os

# --- 設定 ---
st.set_page_config(page_title="Form Sales Assistant", page_icon="📝", layout="centered")

st.title("📝 Form Sales Assistant")
st.markdown("AIを活用したパーソナライズ営業文面ジェネレーター")

# APIキーの取得 (Streamlit Secrets または 環境変数)
api_key = st.secrets.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY")

if not api_key:
    st.error("⚠️ GEMINI_API_KEY が設定されていません。Streamlit CloudのSecretsに設定してください。")
    st.stop()

genai.configure(api_key=api_key)
model = genai.GenerativeModel('gemini-2.5-flash')

def scrape_url(url):
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # 不要なタグを削除
        for script in soup(["script", "style", "noscript", "iframe", "img", "svg"]):
            script.decompose()
            
        text = soup.get_text(separator=' ', strip=True)
        # トークン制限対策として先頭10000文字に制限
        return text[:10000]
    except Exception as e:
        st.warning(f"URLの取得に失敗しました ({url}): {e}")
        return None

def find_related_urls(main_url):
    """公式サイトから関連リンク（採用、ニュース、PR TIMES等）を自動抽出する"""
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        res = requests.get(main_url, headers=headers, timeout=10)
        res.raise_for_status()
        soup = BeautifulSoup(res.content, 'html.parser')
        
        found_urls = []
        target_keywords = ['recruit', 'saiyo', 'news', 'prtimes.jp', 'wantedly.com', 'note.com']
        
        for a in soup.find_all('a', href=True):
            href = a['href']
            full_url = urljoin(main_url, href)
            
            # 関連性が高いキーワードが含まれているかチェック
            if any(keyword in full_url.lower() for keyword in target_keywords):
                # 重複やメインURL自体は避ける
                if full_url not in found_urls and full_url != main_url:
                    found_urls.append(full_url)
                    
            if len(found_urls) >= 4: # 最大4つまで（合計5URLになるように）
                break
                
        return found_urls
    except Exception as e:
        return []

# --- UI ---
st.write("対象企業の公式サイトのURLを入力してください。")

if "url_count" not in st.session_state:
    st.session_state.url_count = 1

# まず「参考URL 1」だけを独立して配置
url_0 = st.text_input("参考URL 1 (公式サイト)", key="url_0")

if st.button("🔍 関連URLを自動検索"):
    if url_0.strip():
        with st.spinner("公式サイトから関連リンクを探索中..."):
            related = find_related_urls(url_0.strip())
            if related:
                # 見つかった分だけ入力欄を増やし、セッションにURLを保存
                st.session_state.url_count = min(5, 1 + len(related))
                for idx, r_url in enumerate(related):
                    st.session_state[f"url_{idx+1}"] = r_url
                st.success(f"{len(related)}件の関連URLを自動設定しました！")
            else:
                st.warning("関連URLが見つかりませんでした。ご自身で追加してください。")
    else:
        st.error("まず「参考URL 1」に公式サイトのURLを入力してください。")

urls = []
if url_0.strip():
    urls.append(url_0.strip())

# 残りのURL入力欄（自動追加された分、または手動追加分）
for i in range(1, st.session_state.url_count):
    # url_0は既に表示したので i+1 (参考URL 2, 3...)
    url = st.text_input(f"参考URL {i+1}", key=f"url_{i}")
    if url.strip():
        urls.append(url.strip())

col1, col2, _ = st.columns([1, 1, 3])
with col1:
    if st.session_state.url_count < 5:
        if st.button("➕ 追加", key="add_url_btn"):
            st.session_state.url_count += 1
            st.rerun()
with col2:
    if st.session_state.url_count > 1:
        if st.button("➖ 減らす", key="remove_url_btn"):
            st.session_state.url_count -= 1
            st.rerun()

if st.button("分析＆文面生成", type="primary"):
    if not urls:
        st.error("少なくとも1つの有効なURLを入力してください。")
    else:
        with st.spinner("サイトから情報を取得し、AIで分析・文面生成を行っています..."):
            texts = []
            for url in urls:
                text = scrape_url(url)
                if text:
                    texts.append(text)
            
            if not texts:
                st.error("有効なテキスト情報が取得できませんでした。")
                st.stop()
            
            combined_text = "\n\n--- 次のページ ---\n\n".join(texts)
            
            prompt = f"""
あなたは非常に優秀なBtoB営業・マーケティングのコンサルタントです。
以下のウェブサイト情報を読み込み、対象企業を特定した上で、指示に従ってJSON形式で結果を出力してください。

【対象企業のウェブサイト情報】
{combined_text}

【タスク1：企業分析】
対象企業について、以下の5つの観点で情報を整理してください。
①事業の強み
②現在力を入れていそうな領域
③直近のニュースやプレスリリースがあれば内容（なければ「特になし」）
④採用ページなどから推測される組織課題
⑤この会社が今抱えていそうなマーケティング課題

【タスク2：フォーム営業の文面作成】
【ルール】
・以下の【理想的な出力例】のトーン＆マナーを完全に模倣すること。過度にへりくだった業者感も、馴れ馴れしい表現も避け、優秀なBtoBのビジネスパーソンとして端的に書く。
・冒頭の1文で"なぜ御社に連絡したのか"の理由を、相手のWebサイトの具体的な事実（事例の数字、設備投資、代表の発言など）を引用して書くこと。
・相手の事業内容や直近の動きに対して、自分がどう貢献できるか（SEO、X運用、リード獲得など）を具体的な成果のイメージと共に1〜2行で提示する。
・自社サービスの説明は最小限に抑え、相手のメリットを中心に書くこと。
・全体を「200字以内」に厳格に収めること。短く簡潔に。
・最後は例にあるような、押し付けがましくないシンプルなクロージングにすること。

【理想的な出力例（このトーンと構成を模倣してください）】
例1（SaaS企業向け）：
「御社の〇〇（サービス名）のLPを拝見しました。導入事例ページで△△社の解約率改善の数字が出ていましたが、あの事例をもっとSEOとXで拡散すれば、同じ課題を持つ企業からの指名検索が月50件以上増えると見ています。同業界で事例コンテンツ起点の指名検索設計をやっていますので、御社でも再現できるかお話しできればと思います。」

例2（製造業向け）：
「御社のコーポレートサイトで、今期の設備投資で〇〇ラインを増設されたことを拝見しました。ちょうど同じ△△業界のBtoB企業で、設備増強のタイミングに合わせてX運用で採用応募と新規取引先の問い合わせを同時に増やした事例がありまして、御社でも使えるかもしれません。もしご興味あればお返事いただけると嬉しいです。」

例3（コンサル会社向け）：
「御社の代表が登壇された〇〇カンファレンスのレポート記事を読みました。"コンサルは答えを出すのではなく、クライアントの問いを磨く仕事だ"という発言が刺さりました。まさにその考え方を体現するX発信を、同業界の経営者向けに設計しています。御社の代表の発信力を、商談獲得と採用の両方に繋げる方法がありますので、5分だけお目通しいただけたらと思いご連絡しました。」

出力は必ず以下のJSONスキーマに従ってください。JSON以外のテキスト（マークダウンのバッククォートなど）は出力しないでください。

{{
  "analysis": {{
    "strengths": "①事業の強み",
    "focusAreas": "②現在力を入れていそうな領域",
    "news": "③直近のニュースやプレスリリース",
    "orgIssues": "④推測される組織課題",
    "marketingIssues": "⑤抱えていそうなマーケティング課題"
  }},
  "draft": "生成されたフォーム営業文面"
}}
"""
            
            try:
                # generate_content with application/json requirement
                # To ensure valid JSON output, we can use generation_config
                response = model.generate_content(
                    prompt,
                    generation_config=genai.types.GenerationConfig(
                        response_mime_type="application/json",
                    )
                )
                
                result_text = response.text
                result = json.loads(result_text)
                
                st.success("生成が完了しました！")
                
                st.subheader("📊 企業分析結果")
                analysis = result.get("analysis", {})
                st.markdown(f"**① 事業の強み:**\n{analysis.get('strengths', '')}")
                st.markdown(f"**② 現在力を入れていそうな領域:**\n{analysis.get('focusAreas', '')}")
                st.markdown(f"**③ 直近のニュース/PR:**\n{analysis.get('news', '')}")
                st.markdown(f"**④ 推測される組織課題:**\n{analysis.get('orgIssues', '')}")
                st.markdown(f"**⑤ 抱えていそうなマーケ課題:**\n{analysis.get('marketingIssues', '')}")
                
                st.subheader("✉️ 生成されたドラフト")
                st.info("AIが作成した文面です。「最後の1行」をあなたの言葉で追記して、よりパーソナライズされた文面に仕上げましょう。")
                draft = result.get("draft", "")
                st.text_area("ドラフト文面", draft, height=200)
                
            except Exception as e:
                st.error(f"エラーが発生しました: {e}")
