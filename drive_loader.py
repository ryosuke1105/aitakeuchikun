import os
import json
import time
import io
import re
import threading
import gc
from typing import List, Dict, Any, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv
import google.generativeai as genai
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

# Load environment variables from .env if present
load_dotenv()

class DriveGeminiService:
    def __init__(self):
        self.drive_folder_id = os.getenv("GOOGLE_DRIVE_FOLDER_ID", "")
        self.gemini_api_key = os.getenv("GEMINI_API_KEY", "")
        self.service_account_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "")
        
        # Cache variables and lock
        self._pdf_cache: List[Dict[str, Any]] = []
        self._cache_timestamp: float = 0.0
        self._cache_ttl: float = 1200.0  # 20 minutes cache TTL
        self._lock = threading.Lock()
        
        # Configure Gemini API if key exists
        if self.gemini_api_key:
            genai.configure(api_key=self.gemini_api_key)

    def _get_drive_service(self):
        """Initialize and return Google Drive API service client."""
        if not self.service_account_json:
            raise ValueError("GOOGLE_SERVICE_ACCOUNT_JSON 環境変数が設定されていません。")
        
        try:
            raw = self.service_account_json.strip()
            if (raw.startswith("'") and raw.endswith("'")) or (raw.startswith('"') and raw.endswith('"')):
                raw = raw[1:-1].strip()

            info = json.loads(raw)
            if isinstance(info, dict) and "private_key" in info:
                pk = info["private_key"]
                if "\\n" in pk:
                    info["private_key"] = pk.replace("\\n", "\n")

            scopes = ['https://www.googleapis.com/auth/drive.readonly']
            credentials = service_account.Credentials.from_service_account_info(info, scopes=scopes)
            return build('drive', 'v3', credentials=credentials)
        except Exception as e:
            print(f"[DriveGeminiService] Auth Exception: {e}")
            raise RuntimeError(f"Google Drive サービスアカウントの認証失敗: {str(e)}")

    def _download_single_pdf(self, service, f) -> Dict[str, Any]:
        """Download and extract a single PDF file with safe error isolation."""
        file_id = f['id']
        file_name = f['name']
        try:
            request = service.files().get_media(fileId=file_id)
            fh = io.BytesIO()
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while not done:
                status, done = downloader.next_chunk()
            
            fh.seek(0)
            pdf_bytes = fh.read()

            # Skip oversized files (>15MB) to keep memory safe
            if len(pdf_bytes) > 15 * 1024 * 1024:
                print(f"[DriveGeminiService] Skipping large PDF ({len(pdf_bytes)} bytes): {file_name}")
                return {'id': file_id, 'name': file_name, 'text': f"[{file_name} は大容量のためスキップ]"}

            extracted_text = self._extract_pdf_text(pdf_bytes, file_name)
            
            # Immediately release heavy binary bytes
            del pdf_bytes
            fh.close()
            gc.collect()

            return {
                'id': file_id,
                'name': file_name,
                'text': extracted_text
            }
        except Exception as e:
            print(f"[DriveGeminiService] Safe skip for {file_name}: {e}")
            return {'id': file_id, 'name': file_name, 'text': f"[{file_name} 読み込みスキップ]"}

    def fetch_all_pdfs(self, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """
        Fetch all PDF files from target folder safely.
        """
        with self._lock:
            now = time.time()
            if not force_refresh and self._pdf_cache and (now - self._cache_timestamp < self._cache_ttl):
                return self._pdf_cache

            if not self.drive_folder_id or not self.service_account_json:
                return self._get_fallback_pdfs()

            t_start = time.time()
            try:
                service = self._get_drive_service()
                query = f"'{self.drive_folder_id}' in parents and mimeType='application/pdf' and trashed=false"
                results = service.files().list(q=query, fields="files(id, name)").execute()
                files = results.get('files', [])

                if not files:
                    return self._get_fallback_pdfs()

                print(f"[DriveGeminiService] Fetching {len(files)} PDFs (Safe mode)...")
                loaded_pdfs = []
                with ThreadPoolExecutor(max_workers=2) as executor:
                    futures = [executor.submit(self._download_single_pdf, service, f) for f in files]
                    for future in as_completed(futures):
                        res = future.result()
                        if res:
                            loaded_pdfs.append(res)

                if loaded_pdfs:
                    self._pdf_cache = loaded_pdfs
                    self._cache_timestamp = now
                    t_end = time.time()
                    print(f"[DriveGeminiService] All {len(loaded_pdfs)} PDFs loaded & cached in {t_end - t_start:.2f}s!")
                    return loaded_pdfs
                else:
                    return self._get_fallback_pdfs()

            except Exception as e:
                print(f"[DriveGeminiService] Failed to load PDFs: {e}")
                return self._get_fallback_pdfs()

    def _extract_pdf_text(self, pdf_bytes: bytes, file_name: str) -> str:
        """Helper to extract plain text from PDF bytes using pypdf safely."""
        try:
            import pypdf
            reader = pypdf.PdfReader(io.BytesIO(pdf_bytes), strict=False)
            text_pages = []
            for idx, page in enumerate(reader.pages):
                try:
                    extracted = page.extract_text() or ""
                    if extracted.strip():
                        text_pages.append(f"--- Page {idx+1} ---\n{extracted}")
                except Exception as page_e:
                    print(f"Page {idx+1} skipped in {file_name}: {page_e}")
                    continue
            return "\n".join(text_pages) if text_pages else f"[{file_name} のテキスト抽出なし]"
        except Exception as e:
            print(f"pypdf extraction skipped for {file_name}: {e}")
            return f"[{file_name} のテキスト抽出なし]"


    def _get_fallback_pdfs(self) -> List[Dict[str, Any]]:
        """Fallback demo documents when Drive API is not connected."""
        return [
            {
                'id': 'demo-1',
                'name': 'サイバーセキュリティ＆夢カワイイ運用ガイド.pdf',
                'text': """
                [資料1: サイバーセキュリティ＆原宿ゆめかわいい運用規定]
                第1条（目的）: 本アプリは、サイバー空間の厳重なセキュリティ認証と、ユーザーを癒すゆめかわいいUXを融合した高度認証Q&Aシステムである。
                第2条（認証コード）: システムアクセスに必要なコードは暗証キー（デフォルト: CYBER_SECRET_2026）である。認証失敗時はサイバー警告を発する。
                第3条（PDF横断解析）: Google Drive内の全PDFをコンテキストとしてGemini APIが自動解析し、文字数制限内で回答を生成する。
                """
            },
            {
                'id': 'demo-2',
                'name': '原宿魔法少女Q&Aマニュアル.pdf',
                'text': """
                [資料2: 原宿パステル魔法マニュアル]
                ・ゆめかわいい世界観では、ミルキーピンク(#FFDBE5)、パステルラベンダー(#E8D5FF)、ミントグリーン(#D0F4DE)を基調とする。
                ・Geminiちゃんはユーザーの質問に対して、ドライブ内のPDFをすみずみまで参照し、正確かつ可愛く簡潔に答える魔法を持つ。
                ・文字数指定（10〜1000文字）は絶対厳守であり、文末が途切れずに自然な日本語で締めくくられる。
                """
            }
        ]

    def _filter_relevant_docs(self, pdfs: List[Dict[str, Any]], question: str, max_docs: int = 8) -> List[Dict[str, Any]]:
        """Filter the most relevant PDF documents matching the user question keywords for sub-2s responses."""
        if len(pdfs) <= max_docs:
            return pdfs

        keywords = [w.strip() for w in re.split(r'[\s,、。！？!?\n]+', question) if len(w.strip()) > 1]
        if not keywords:
            return pdfs[:max_docs]

        scored_pdfs = []
        for pdf in pdfs:
            text = pdf.get('text', '')
            name = pdf.get('name', '')
            score = 0
            for kw in keywords:
                score += text.count(kw) * 2
                score += name.count(kw) * 10
            scored_pdfs.append((score, pdf))

        scored_pdfs.sort(key=lambda x: x[0], reverse=True)
        top_matched = [pdf for score, pdf in scored_pdfs if score > 0]
        if top_matched:
            return top_matched[:max_docs]
        else:
            return pdfs[:max_docs]

    def ask_gemini(self, question: str, max_chars: int = 300) -> Dict[str, Any]:
        """
        Query Gemini model using PDF files/texts from Drive with character limit constraints.
        """
        if not self.gemini_api_key:
            # Mock Gemini response if API key is absent
            mock_answer = self._generate_mock_answer(question, max_chars)
            return {
                "answer": mock_answer,
                "char_count": len(mock_answer),
                "max_chars": max_chars,
                "document_count": len(self.fetch_all_pdfs()),
                "sources": [doc["name"] for doc in self.fetch_all_pdfs()],
                "is_mock": True
            }

        all_pdfs = self.fetch_all_pdfs()

        # Fast Relevance Filtering: Filter 100 PDFs down to the top relevant ones for the question
        pdfs = self._filter_relevant_docs(all_pdfs, question, max_docs=8)
        print(f"[DriveGeminiService] Question matched top {len(pdfs)} relevant PDFs out of {len(all_pdfs)} total PDFs")

        # Build clean text context from loaded PDFs (fast & lightweight payload)
        context_blocks = []
        fallback_pdf_parts = []


        for pdf in pdfs:
            doc_name = pdf['name']
            doc_text = pdf.get('text', '').strip()
            pdf_bytes = pdf.get('bytes')
            
            if doc_text and not doc_text.startswith("[テキスト抽出なし]"):
                context_blocks.append(f"=== ドキュメント: {doc_name} ===\n{doc_text}\n")
            elif pdf_bytes:
                # Only attach raw binary bytes if text extraction was empty/failed
                fallback_pdf_parts.append(f"=== PDF添付資料: {doc_name} ===")
                fallback_pdf_parts.append({"mime_type": "application/pdf", "data": pdf_bytes})

        full_context = "\n".join(context_blocks)

        system_instruction = (
            "あなたはGoogle Drive上の複数PDF資料を横断解析する優秀かつ親切なAIアシスタントです。\n"
            "【必須守則】\n"
            "1. 提供された複数のPDF資料の内容を直接の根拠として質問に正確に回答してください。\n"
            "2. 回答は必ず指定された文字数（" + str(max_chars) + "文字以内）を厳密に遵守してください。\n"
            "3. 途中で文章が途切れたり丸括弧が開いたまま終わったりせず、指定文字数以内で完結した自然な日本語を作成してください。\n"
            "4. 余計な前置きは省き、要点を分かりやすくまとめてください。"
        )

        user_prompt_text = (
            f"【参照ドキュメントテキスト群】\n{full_context}\n\n"
            f"【ユーザーからの質問】\n{question}\n\n"
            f"【文字数指定】\n絶対に {max_chars} 文字以内の完結した日本語で回答してください。"
        )

        # Use fast text-only prompt if text context exists, otherwise attach fallback PDF parts
        if fallback_pdf_parts:
            gemini_payload = [user_prompt_text] + fallback_pdf_parts
        else:
            gemini_payload = user_prompt_text

        try:
            candidate_names = [
                "gemini-2.5-flash",
                "gemini-3.6-flash",
                "gemini-3.5-flash",
                "gemini-flash-latest",
                "gemini-2.5-pro",
                "gemini-pro-latest"
            ]

            response = None
            last_err = None
            used_model_name = ""

            for name in candidate_names:
                try:
                    model = genai.GenerativeModel(
                        model_name=name,
                        system_instruction=system_instruction
                    )
                    print(f"[DriveGeminiService] Querying Gemini ({name}) with optimized payload...")
                    res = model.generate_content(
                        gemini_payload,
                        generation_config=genai.types.GenerationConfig(
                            temperature=0.3,
                            max_output_tokens=1500
                        )
                    )
                    if res and res.text:
                        response = res
                        used_model_name = name
                        print(f"[DriveGeminiService] Success with model: {name}")
                        break
                except Exception as e:
                    print(f"[DriveGeminiService] Candidate model '{name}' error: {e}")
                    last_err = e
                    continue

            if not response:
                raise RuntimeError(f"Geminiモデルでの回答生成に失敗しました: {last_err}")


            raw_answer = response.text.strip()
            
            # Post-processing enforcement of character count safety
            final_answer = self._enforce_character_limit(raw_answer, max_chars)

            return {
                "answer": final_answer,
                "char_count": len(final_answer),
                "max_chars": max_chars,
                "document_count": len(pdfs),
                "sources": [pdf["name"] for pdf in pdfs],
                "is_mock": False
            }

        except Exception as e:
            print(f"Gemini API Exception: {e}")
            err_str = str(e)
            if "404" in err_str or "not found" in err_str:
                fallback_msg = (
                    "【APIキー設定エラー】\n"
                    "Google AI Studioの有効なAPIキーが設定されていない可能性があります。\n"
                    "Google AI Studio (https://aistudio.google.com/) で発行した「AIzaSy」から始まるAPIキーを .env の GEMINI_API_KEY に設定してください。"
                )
            else:
                fallback_msg = f"Gemini API処理エラー: {err_str}"

            return {
                "answer": self._enforce_character_limit(fallback_msg, max_chars),
                "char_count": len(fallback_msg),
                "max_chars": max_chars,
                "document_count": len(pdfs),
                "sources": [pdf["name"] for pdf in pdfs],
                "is_mock": True
            }




    def _enforce_character_limit(self, text: str, max_chars: int) -> str:
        """
        Safely trim text to strictly <= max_chars without breaking sentence flow.
        """
        text = text.strip()
        if len(text) <= max_chars:
            return text

        truncated = text[:max_chars]
        # Look for punctuation near the end to end gracefully
        punctuations = ['。', '！', '？', '\n', '.', '!', '?']
        last_punct = -1
        for p in punctuations:
            idx = truncated.rfind(p)
            if idx > last_punct:
                last_punct = idx

        if last_punct > int(max_chars * 0.5):
            return truncated[:last_punct + 1]
        else:
            return truncated + "..."

    def _generate_mock_answer(self, question: str, max_chars: int) -> str:
        """Generate cute mock answer when API keys are not provided."""
        sources = [doc["name"] for doc in self.fetch_all_pdfs()]
        mock_text = (
            f"💖【Google Drive横断参照デモ結果】💖\n"
            f"「{question}」についての回答です✨\n"
            f"Drive内の資料（{', '.join(sources)}）を参照しました！\n"
            f"本アプリはサイバー認証を突破したあなた専用のQ&A端末です。"
            f"GEMINI_API_KEYを.envに設定すると、実際のAIによる高度な複数PDF横断解析が行われます♪"
        )
        return self._enforce_character_limit(mock_text, max_chars)
