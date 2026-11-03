##-- vector_store.py --

import os
from pathlib import Path
from langchain_openai import OpenAIEmbeddings
from langchain_chroma import Chroma
from langchain_community.document_loaders import PyPDFLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from openai import OpenAI
from dotenv import load_dotenv
from langchain_core.documents import Document
from tqdm import tqdm
from docx import Document as DocxDocument
from lxml import etree
from copy import deepcopy
from model_config import OPENAI_CHAT_MODEL, OPENAI_EMBEDDING_MODEL, log_openai_model

APP_ROOT = Path(__file__).resolve().parent
CHROMA_DIR = APP_ROOT / "chroma_index"
DOCS_DIR = APP_ROOT / "documents"

load_dotenv()

def add_section_metadata(chunks):
    updated_chunks = []
    current_section = "Unknown"

    for chunk in chunks:
        lines = chunk.page_content.splitlines()
        for line in lines:
            if line.strip().startswith("#"):
                current_section = line.strip().lstrip("#").strip()
                break  # use first heading in chunk

        new_chunk = deepcopy(chunk)
        new_chunk.metadata["section"] = current_section
        updated_chunks.append(new_chunk)

    return updated_chunks


def read_docx_file(file_path):
    doc = DocxDocument(file_path)
    full_text = []

    for para in doc.paragraphs:
        style = para.style.name.lower()

        # Add section titles with Markdown-style headers
        if "heading" in style:
            level = ''.join(filter(str.isdigit, style)) or "1"
            heading_prefix = "#" * min(int(level), 6)
            full_text.append(f"{heading_prefix} {para.text.strip()}")
            continue

        if para.text.strip():
            full_text.append(para.text.strip())

        # Check for images in runs
        for run in para.runs:
            if 'graphic' in run._element.xml:
                try:
                    tree = etree.fromstring(run._element.xml.encode('utf-8'))
                    descr_el = tree.xpath('//pic:cNvPr', namespaces={
                        'pic': 'http://schemas.openxmlformats.org/drawingml/2006/picture'
                    })
                    if descr_el and 'descr' in descr_el[0].attrib:
                        alt_text = descr_el[0].attrib['descr'].strip()
                        full_text.append(f"[Image: {alt_text}]")
                except Exception as e:
                    print(f"⚠️ Failed to extract alt text: {e}")

    # Extract table data
    for table in doc.tables:
        for row in table.rows:
            row_data = [cell.text.strip() for cell in row.cells]
            if any(row_data):
                full_text.append(" | ".join(row_data))  # Markdown-style row

    return "\n".join(full_text)




def build_vector_store():
    documents = []

    # Load PDFs
    pdf_files = [f for f in os.listdir(DOCS_DIR) if f.endswith(".pdf")]
    for filename in pdf_files:
        path = DOCS_DIR / filename
        loader = PyPDFLoader(str(path))
        for doc in loader.load():
            doc.metadata["file"] = filename
            doc.metadata["type"] = "pdf"
            documents.append(doc)

    # Load DOCX files
    docx_files = [f for f in os.listdir(DOCS_DIR) if f.endswith(".docx")]
    for filename in docx_files:
        path = DOCS_DIR / filename
        text = read_docx_file(path)
        documents.append(Document(page_content=text, metadata={"file": filename, "type": "docx"}))

    if not documents:
        print("⚠️ No documents found in the 'documents/' directory.")
        return None


    bilingual_documents = []

    for doc in tqdm(documents, desc="🔄 Preparing bilingual documents"):
        content = doc.page_content.strip()
        is_arabic = any('؀' <= char <= 'ۿ' for char in content)

        is_arabic = any('\u0600' <= char <= '\u06FF' for char in content)

        # Always include the original document (Arabic or English)
        bilingual_documents.append(doc)

        # If Arabic, also add its English translation
        if is_arabic:
            try:
                client = OpenAI()
                log_openai_model("vector_store_document_translation", OPENAI_CHAT_MODEL)
                response = client.chat.completions.create(
                    model=OPENAI_CHAT_MODEL,
                    messages=[
                        {"role": "system", "content": "Translate the following Arabic content to English."},
                        {"role": "user", "content": content}
                    ]
                )
                translated_text = response.choices[0].message.content.strip()
                bilingual_documents.append(Document(
                    page_content=translated_text,
                    metadata={**doc.metadata, "lang": "en", "source": "translated"}
                ))
            except Exception as e:
                print(f"⚠️ Translation failed: {e}")
                # optionally re-add the Arabic-only version again if needed

                

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200,
        separators=["\n\n", "\n", ".", "؟", "،"]
    )

    chunks = splitter.split_documents(bilingual_documents)
    chunks = add_section_metadata(chunks)
    
    embeddings = OpenAIEmbeddings(model=OPENAI_EMBEDDING_MODEL)
    vectorstore = Chroma.from_documents(chunks, embedding=embeddings, persist_directory=str(CHROMA_DIR))
    print(f"✅ Vector store built from {len(pdf_files)} PDFs and {len(docx_files)} DOCX files, saved to '{CHROMA_DIR}'")

def load_vector_store():
    embeddings = OpenAIEmbeddings(model=OPENAI_EMBEDDING_MODEL)
    return Chroma(persist_directory=str(CHROMA_DIR), embedding_function=embeddings)
