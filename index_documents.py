import os
import subprocess
import re
from langchain_community.document_loaders import UnstructuredWordDocumentLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.embeddings import HuggingFaceEmbeddings
from langchain.vectorstores.faiss import FAISS

# ========== CONFIG ==========
MODE = "testing"    # "testing" (per-chunk embedding with progress prints) or "production" (batch)
EMBED_MODEL = "all-MiniLM-L6-v2"  # SBERT: fast, accurate, local
# ============================

def table_text_to_markdown(text):
    rows = [row for row in text.strip().split('\n') if row.strip()]
    table = []
    for row in rows:
        if '\t' in row:
            table.append([cell.strip() for cell in row.split('\t')])
        else:
            table.append([cell.strip() for cell in re.split(r'\s{2,}', row)])
    table = [r for r in table if any(cell for cell in r)]
    if not table or len(table[0]) < 2:
        return text
    header = table[0]
    aligns = ['---'] * len(header)
    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join(aligns) + " |"
    ]
    for row in table[1:]:
        row = list(row) + [''] * (len(header) - len(row))
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)

def clean_chunk_text(text):
    text = re.sub(r"[^\x20-\x7E\n\t]", "", text)
    text = re.sub(r"\n\s*\n", "\n\n", text)
    text = "\n".join(line.rstrip() for line in text.splitlines())
    text = text.strip()
    return text

def extract_entities(text):
    date_pattern = r"\b(?:\d{1,2}\s+\w+\s+\d{4}|\w+\s+\d{1,2},\s+\d{4}|\d{4}-\d{2}-\d{2})\b"
    name_pattern = r"\b[A-Z][a-z]+\s+[A-Z][a-z]+\b"
    record_pattern = r"\b(?:[A-Z0-9#-]{6,})\b"

    dates = re.findall(date_pattern, text)
    names = re.findall(name_pattern, text)
    records = re.findall(record_pattern, text)
    underlined = []
    return dates, names, records, underlined

docs_path = "./SOPs/"

# 1. Convert all .doc files to .docx in the same folder
for file in os.listdir(docs_path):
    if file.endswith(".doc") and not file.endswith(".docx"):
        in_path = os.path.join(docs_path, file)
        print(f"Converting {file} to .docx in place...")
        subprocess.run([
            "soffice", "--headless", "--convert-to", "docx", in_path, "--outdir", docs_path
        ], check=True)

# 2. Load all .docx files (including converted)
documents = []
for file in os.listdir(docs_path):
    if file.endswith(".docx"):
        print(f"Loading {file} ...")
        loader = UnstructuredWordDocumentLoader(
            os.path.join(docs_path, file),
            mode="elements"
        )
        documents.extend(loader.load())

print(f"Loaded {len(documents)} elements from all .docx files.")

# 3. Chunk documents
splitter = RecursiveCharacterTextSplitter(chunk_size=400, chunk_overlap=50)
chunks = splitter.split_documents(documents)
print(f"Split into {len(chunks)} chunks.")

if len(chunks) == 0:
    print("ERROR: No document chunks to embed! Check loader and chunking step.")
    for i, doc in enumerate(documents[:3]):
        print(f"\nDoc {i+1} preview:", doc.page_content[:100])
    exit(1)

def is_table_chunk(chunk, text):
    meta_category = ""
    if hasattr(chunk, "metadata"):
        meta_category = str(chunk.metadata.get("category", "")).lower()
    meta_is_table = meta_category == "table"
    heur_is_table = ('\t' in text or re.search(r'\s{2,}', text))
    return meta_is_table or heur_is_table, meta_is_table, heur_is_table

for i, chunk in enumerate(chunks):
    text = chunk.page_content
    text = clean_chunk_text(text)
    is_table, by_meta, by_heur = is_table_chunk(chunk, text)
    if is_table:
        chunk.page_content = table_text_to_markdown(text)
        reason = []
        if by_meta:
            reason.append("metadata")
        if by_heur:
            reason.append("heuristic")
        debug_msg = f"[CHUNK {i+1}] Converted to Markdown table (reason: {', '.join(reason)})"
    else:
        chunk.page_content = text
        debug_msg = f"[CHUNK {i+1}] No table conversion"
    # ENTITY EXTRACTION FOR METADATA
    dates, names, records, underlined = extract_entities(chunk.page_content)
    if hasattr(chunk, "metadata") and isinstance(chunk.metadata, dict):
        chunk.metadata["dates"] = dates
        chunk.metadata["names"] = names
        chunk.metadata["records"] = records
        chunk.metadata["underlined"] = underlined
    if i < 5 or i % 50 == 0:
        print(debug_msg)
        print("Preview:", repr(chunk.page_content[:120]))
        if hasattr(chunk, "metadata"):
            print("Metadata (preview):", {k: v for k, v in chunk.metadata.items() if k in ["dates","names","records","underlined","heading","source"]})

# 5. Embedding and FAISS index (SBERT)
embeddings = HuggingFaceEmbeddings(model_name=EMBED_MODEL)

if MODE == "testing":
    docs_for_faiss = []
    embeddings_list = []
    print("Embedding each chunk individually (testing mode)...")
    for i, chunk in enumerate(chunks):
        text = chunk.page_content.strip()
        if not text:
            print(f"[EMBEDDING] Skipping empty chunk {i+1}")
            continue
        try:
            vector = embeddings.embed_documents([text])
            if not vector or not vector[0]:
                print(f"[EMBEDDING] No embedding returned for chunk {i+1}, skipping.")
                continue
            embeddings_list.append(vector[0])
            docs_for_faiss.append(chunk)
            if i < 5 or i % 20 == 0 or i == len(chunks) - 1:
                print(f"[EMBEDDING] Embedded chunk {i+1}/{len(chunks)}; text preview: {repr(text[:60])}")
        except Exception as e:
            print(f"[EMBEDDING] Error embedding chunk {i+1}: {e}")
            print(f"Text was: {repr(text[:120])}")

    print(f"Chunks embedded: {len(embeddings_list)}")
    print(f"Chunks with docs: {len(docs_for_faiss)}")
    if not docs_for_faiss:
        print("ERROR: No valid chunks for FAISS indexing.")
        exit(1)
    print("Indexing with FAISS from documents...")
    vectorstore = FAISS.from_documents(docs_for_faiss, embeddings)
else:
    print("Embedding all chunks in batch (production mode)...")
    vectorstore = FAISS.from_documents(chunks, embeddings)
    print("Batch embedding complete.")

vectorstore.save_local("faiss_index")
print("Vector index created and saved as 'faiss_index'.")
