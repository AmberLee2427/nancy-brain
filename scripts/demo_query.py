# demo_query.py
import sys
import requests
import os
from pathlib import Path
import json
import re

from bot.plugins.rag.rag_service import get_rag_service
import yaml
import difflib

debug = False

query = " ".join(sys.argv[1:]) or "submission validation"
rag = get_rag_service()
if not rag.is_available():
    print("RAG service not available. Build the knowledge base first.\n")
    sys.exit(1)
else:
    print("RAG service is available.\n")

print(f"Query: '{query}'\n\n")

results = rag.search(query, limit=5)
if debug:
    for i, result in enumerate(results, 1):
        print(f"Result {i}:")
        print(f"  File: {result['id']}")
        print(f"  Retrieval score: {result['score']:.3f}")
        print(f"  Extension weight: {result.get('extension_weight', 1.0):.3f}")
        print(f"  Model weight: {result.get('model_score', 1.0):.3f}")
        print(f"  Final score: {result.get('adjusted_score', result['score']):.3f}")
        print(f"  Content length: {len(result['text'])} chars")
        print(f"  Content preview: {result['text'][:1000]}...")
        print()

# System prompt
system_prompt = """
You are a helpful Slack-based assistant that can answer questions about an indexed microlensing-related knowledge base.
Your users are Slack users who do not have immediate access to your knowledge base.
You will receive faiss results from a search to assist with a user query.
Prioritize the results in your response over your inherent assumptions. 
Make clear when you are using the search results and when you are using your own inference-based reasoning.


Tools:
* If you need more detail, you can ask to see a specific file using:
    [RETRIEVE: <file_path>]
  If a file retrieval fails, you will receive a "Did you mean..." message with similar file paths. Use these suggestions to refine your next request.
* You can reweight the search results by adjusting your score multiplier (min 0.5, max 2.0).
    [WEIGHT: <file_path>, <score_multiplier>]
  This weight should consider usefulness of the file for general user's query, not relevance to the current query.
* You can initiate a new search by adding:
  [SEARCH: <query> limit n]
  - <query> can be a simple keyword/phrase search (e.g., FSPL MulensModel setup parameters limit 5)
  - OR a SQL-like query using LIKE, AND, OR (e.g., select id, text from txtai where text like '%FSPL%' and text like '%MulensModel%' limit 5)
  - For both natural language and SQL queries, always use the format [SEARCH: <query> limit n].
  - Do NOT use natural language boolean logic (e.g., do not use: "FSPL" AND "MulensModel" AND "setup" OR "parameters")
  - If you use SQL, you must use the correct SQL syntax (see above) and always include a LIMIT clause.
* You can request a directory listing using 
    [TREE: <directory>]. 
  This will show you all files and subdirectories in that location, relative to the knowledge base root.
* Comments in a "RESPONSE:" block will be sent to the user.
    [BEGIN RESPONSE]
    <comment>
    [END RESPONSE]
  Consider any other assistant text to be your internal monologue. 
  ONLY text in the "RESPONSE" block will be sent to the user.
  You do not need to include a RESPONSE tool call in every turn.
  Every RESPONSE will be sent to the user immediately.
  However, you should ensure you have a response before the turn limit is reached or using the AWAIT tool.
* To end your internal reasoning turns early (before the turn limit is reached), add:
    [AWAIT]
  This will send your response to the user and await further instructions.
  You should use this when you feel you require further information from the user in order to complete your task well.
  You should also use this if you have provided a comprehensive response and do not require any more information.
The order of tool calls in unimportant. However, your weighting will always be applied before a new search is performed.



Example:
```
user query: 
What is the purpose of the `microlens-submit` package?
...
assistant: 
The search results don't directly explain the purpose of the `microlens-submit` package. 
I need to see the contents of these mentioned files.

[RETRIEVE: microlens_submit/microlens-submit/docs/index.rst]
[RETRIEVE: microlens_submit/microlens-submit/README.md] 

[TREE: microlens_submit/microlens-submit/]

[BEGIN RESPONSE] 
Let me take a look through some of the package documentation...
[END RESPONSE]
...
```


Guidlines:
- If you refer to a file, and a GitHub URL is available, include the link in your response using Slack markdown: 
    <https://github.com/userName/repoName/blob/master/path/to/file/filename.py|filename.py>.
  (Note. make sure you use "master" as the branch name, not "main".)
- The user does not have direct access to the files in your knowledge base, but you can provide GitHub links for reference.
- Format your responses using Slack markdown: *bold*, _italic_, code blocks (```), and Slack-style links. Do not use markdown tables or images.
"""

# prompt the LLM (Gemini) API with the system prompt, query and results

# Format the context from the results
context = ""
for i, result in enumerate(results, 1):
    github_url = rag._get_github_url(result['id'])
    if github_url:
        slack_link = f"<{github_url}|{Path(result['id']).name}>"
        context += f"Result {i}:\nFile: {result['id']} ({slack_link})\nScore: {result['score']:.3f}\nContent:\n{result['text']}\n\n"
    else:
        context += f"Result {i}:\nFile: {result['id']}\nScore: {result['score']:.3f}\nContent:\n{result['text']}\n\n"

# Track files already included in the context window
context_files = set(result['id'] for result in results)

searching = True
max_turns = 5
turn = 0
llm_responses = []

# Build a list of all indexed file paths from the embeddings database (once)
all_indexed_docs = list(rag.embeddings.database.search("select id, text from txtai"))
all_indexed_files = [doc['id'] for doc in all_indexed_docs]
indexed_file_map = {doc['id']: doc['text'] for doc in all_indexed_docs}

# Compose the full prompt
full_prompt = f"""{system_prompt}
You will have {max_turns} turns to answer the user's question.

User query:
{query}

Please answer the user's question using the information below.

Relevant search results:
{context}
"""

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GEMINI_MODEL = "gemini-1.5-pro"
GEMINI_API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
headers = {"Content-Type": "application/json"}

model_weights_path = Path("config/model_weights.yaml")
# Load model weights
if model_weights_path.exists():
    with open(model_weights_path, "r") as f:
        model_weights = yaml.safe_load(f) or {}
else:
    model_weights = {}

payload = {
    "contents": [
        {"role": "user", "parts": [{"text": full_prompt}]}
    ]
}

while searching and turn < max_turns:

    response = requests.post(
        f"{GEMINI_API_URL}?key={GEMINI_API_KEY}",
        headers=headers,
        json=payload
    )

    #save payload to file for debugging
    with open(f"tests/payload_{turn}.json", "w") as f:
        json.dump(payload, f)

    if response.ok:
        data = response.json()
        llm_text = data['candidates'][0]['content']['parts'][0]['text']
        if debug:
            print("LLM Response:\n", llm_text)
        assistant_response = f"\n\nTURN {turn+1}:\n\n"
        assistant_response += llm_text + "\n"
    else:
        print("Error:", response.text)
        break

    meta_prompt = f"\n\nTURN {turn+1} REQUESTS:\n\n"

    # RETRIEVE tool handler
    # Extract the file path(s) from the LLM response
    file_paths = []
    if "RETRIEVE:" in llm_text:
        # Support multiple RETRIEVE: lines
        lines = llm_text.splitlines()
        for line in lines:
            if "RETRIEVE:" in line:
                path = line.split("RETRIEVE:")[1].strip().split()[0].rstrip("]")
                file_paths.append(path)
        print(f"\nRetrieving files: {file_paths}")

        # Try to retrieve the file content for each file
        for file_path in file_paths:
            try:
                # Skip if file already in context
                if file_path in context_files:
                    print(f"\nSkipping duplicate file retrieval for '{file_path}' (already in context)")
                    continue
                # Exact match in indexed files
                matching_chunks = [doc_id for doc_id in all_indexed_files if doc_id == file_path]
                if matching_chunks:
                    if debug:
                        print(f"Found {len(matching_chunks)} matching indexed chunks for '{file_path}':")
                    for chunk_id in matching_chunks:
                        if debug:
                            print(f"  - {chunk_id}")
                    file_content = "\n\n".join(indexed_file_map[chunk_id] for chunk_id in matching_chunks)
                    # No character limit: send full file content
                    github_url = rag._get_github_url(matching_chunks[0])
                    if github_url:
                        slack_link = f"<{github_url}|{Path(matching_chunks[0]).name}>"
                        meta_prompt += f"\n\nGitHub URL: {slack_link}"
                    if debug:
                        print(f"file_content: {file_content[:500]}...")
                    # Add to context_files to prevent future duplicates
                    context_files.update(matching_chunks)
                else:
                    # Suggest similar indexed files
                    suggestions = difflib.get_close_matches(file_path, all_indexed_files, n=5, cutoff=0.6)
                    if suggestions:
                        meta_prompt += f"\n\nDid you mean: {', '.join(suggestions)}"
                    file_content = f"[File not found in index. Searched: {file_path}]"
                    if debug:
                        print(f"File content: {file_content[:500]}...")
                meta_prompt += f"\n\nRetrieved file: {file_path}\nFile content:\n{file_content}"
            except Exception as e:
                print(f"Error retrieving file: {e}")
                searching = False

    # WEIGHT tool handler
    if "WEIGHT:" in llm_text:
        lines = llm_text.splitlines()
        meta_prompt += f"\n\nModel reweighting:"
        for line in lines:
            if "WEIGHT:" in line:
                path = line.split("WEIGHT:")[1].strip().split()[0].rstrip("]")
                score_str = line.split("WEIGHT:")[1].strip().split()[1].rstrip("]")
                score_multiplier = float(score_str)
                print(f"\nWeighting file: {path} with multiplier: {score_multiplier}")
                model_weights[path] = score_multiplier
                meta_prompt += f"\nWeighting file: {path} with multiplier: {score_multiplier}"
        with open(model_weights_path, "w") as f:
            yaml.safe_dump(model_weights, f)
        # Reload weights in RAG service for next turn
        rag.model_weights = model_weights

    # TREE tool handler
    if "TREE:" in llm_text:
        lines = llm_text.splitlines()
        for line in lines:
            if "TREE:" in line:
                tree_dir = line.split("TREE:")[1].strip().split()[0].rstrip("]")
                # Build virtual tree from indexed files
                tree_dir = tree_dir.rstrip("/")
                subdirs = set()
                files = []
                prefix = tree_dir + "/" if tree_dir else ""
                for doc_id in all_indexed_files:
                    if doc_id.startswith(prefix):
                        rest = doc_id[len(prefix):]
                        if "/" in rest:
                            subdir = rest.split("/")[0]
                            subdirs.add(subdir)
                        else:
                            files.append(rest)
                entries = [f"[DIR] {d}/" for d in sorted(subdirs)] + [f"      {f}" for f in sorted(files)]
                if entries:
                    meta_prompt += f"\n\nTREE: Listing for '{tree_dir}':\n" + "\n".join(entries)
                    print(f"\nTREE: Listing for '{tree_dir}':\n" + "\n".join(entries))
                else:
                    meta_prompt += f"\n\nTREE: Directory '{tree_dir}' not found or empty in index."
                    print(f"\nTREE: Directory '{tree_dir}' not found or empty in index.")

    # SEARCH tool handler
    # Perform a new search if the assistant has requested it
    if "SEARCH:" in llm_text:
        lines = llm_text.splitlines()
        for line in lines:
            if "SEARCH:" in line:
                search_content = line.split("SEARCH:")[1].strip()
                raw_query = search_content
                if raw_query.lower().startswith('select'):
                    query_part = raw_query
                    print(f"\nNew search (SQL): {query_part}")
                    results = list(rag.embeddings.database.search(query_part))
                else:
                    # For natural language queries, expect format: <query> limit N
                    parts = raw_query.split()
                    llm_search_max_results = int(parts[-1]) if parts[-1].isdigit() else 5
                    # Remove the trailing ' limit N' (8 chars) from the end
                    query_part = raw_query[:-8]
                    print(f"\nNew search (NL): {query_part} (limit {llm_search_max_results})")
                    results = rag.search(query_part, limit=llm_search_max_results)

                # Print the new results with score breakdown
                for i, result in enumerate(results, 1):
                    if debug:
                        print(f"Result {i}:")
                        print(f"  File: {result['id']}")
                        print(f"  Retrieval score: {result.get('score', 0.0):.3f}")
                        print(f"  Extension weight: {result.get('extension_weight', 1.0):.3f}")
                        print(f"  Model weight: {result.get('model_score', 1.0):.3f}")
                        print(f"  Final score: {result.get('adjusted_score', result.get('score', 0.0)):.3f}")
                        print(f"  Content length: {len(result['text'])} chars")
                        print(f"  Content preview: {result['text'][:1000]}...")
                        print()
                    
                # Update the context for the next turn
                meta_prompt += f"\n\nSearch results:\n{query_part}\n"
                for i, result in enumerate(results, 1):
                    github_url = rag._get_github_url(result['id'])
                    if github_url:
                        slack_link = f"<{github_url}|{Path(result['id']).name}>"
                        meta_prompt += f"\n\nResult {i}:\n"
                        meta_prompt += f"  File: {result['id']} ({slack_link})\n"
                    else:
                        meta_prompt += f"\n\nResult {i}:\n"
                        meta_prompt += f"  File: {result['id']}\n"
                    meta_prompt += f"  Score: {result.get('score', 0.0):.3f}\n"
                    meta_prompt += f"  Extension weight: {result.get('extension_weight', 1.0):.3f}\n"
                    meta_prompt += f"  Model weight: {result.get('model_score', 1.0):.3f}\n"
                    meta_prompt += f"  Final score: {result.get('adjusted_score', result.get('score', 0.0)):.3f}\n"
                    meta_prompt += f"  Content length: {len(result['text'])} chars\n"
                    meta_prompt += f"  Content: {result['text']}"

    # RESPONSE tool handler
    # Extract the comment from the LLM response
    # [BEGIN RESPONSE]
    # <comment>
    # [END RESPONSE]
    match = re.search(r"\[BEGIN RESPONSE\](.*?)\[END RESPONSE\]", llm_text, re.DOTALL)
    comment = match.group(1).strip() if match else None
    print(f"\nAssistant response: {comment}")

    llm_responses.append(llm_text)

    payload["contents"].append({"role": "assistant", "parts": [{"text": assistant_response}]})
    payload["contents"].append({"role": "user", "parts": [{"text": meta_prompt}]})

    if "SEARCH:" not in llm_text and "RETRIEVE:" not in llm_text and "TREE:" not in llm_text and "WEIGHT:" not in llm_text and "RESPONSE" in llm_text:
        searching = False

    # AWAIT tool handler
    if "[AWAIT]" in llm_text:
        searching = False
        print(f"\nAwaiting user input...")

    turn += 1

print("\n\n\nLLM Responses:")
for i, response in enumerate(llm_responses, 1):
    print(f"\nResponse {i}:")
    print(response)
