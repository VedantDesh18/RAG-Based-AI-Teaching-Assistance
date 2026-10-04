import pandas as pd
from videoqa.config import config
from videoqa.core.indexer import create_embedding
from videoqa.core.generator import generate_response
from videoqa.vectorstore.chroma import search_vectors

def retrieve(query: str):
    question_embedding = create_embedding([query])[0]
    
    top_k = config['retrieval']['top_k']
    threshold = config['retrieval']['abstention_threshold']
    
    results = search_vectors(question_embedding, top_k=top_k)
    
    if not results:
        return {"answer": "I couldn't find relevant content in this video for your question.", "citations": []}
        
    max_score = results[0]['similarity']
    
    if max_score < threshold:
        return {"answer": "I couldn't find relevant content in this video for your question.", "citations": []}
    
    new_df = pd.DataFrame(results)
    # The prompt requires specific columns
    prompt = f'''I am teaching Node js course. Here are video subtitle chunks containing video title, video number, start time in seconds, end time in seconds, the text at that time:

{new_df[["title", "start_seconds", "end_seconds", "text"]].to_json(orient="records")}
---------------------------------
"{query}"
User asked this question related to the video chunks, you have to answer in a human way (dont mention the above format, its just for you) where and how much content is taught in which video (in which video and at what timestamp) and guide the user to go to that particular video. If user asks unrelated question, tell him that you can only answer questions related to the course
'''
    
    response = generate_response(prompt)
    return {"answer": response, "citations": new_df.to_dict(orient="records")}

if __name__ == "__main__":
    import sys
    query = sys.argv[1] if len(sys.argv) > 1 else "What is forEach?"
    res = retrieve(query)
    print(res["answer"])
