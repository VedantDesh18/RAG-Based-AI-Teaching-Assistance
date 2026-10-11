import json
import os
import sys
import numpy as np
import yaml

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from videoqa.core.indexer import create_embedding
from videoqa.vectorstore.chroma import search_vectors
from videoqa.config import config

def is_relevant(chunk, spans):
    for span in spans:
        if chunk['video_id'] == span['video_id']:
            # Check for overlap
            overlap_start = max(chunk['start_seconds'], span['start_seconds'])
            overlap_end = min(chunk['end_seconds'], span['end_seconds'])
            if overlap_start < overlap_end:
                return True
    return False

def main():
    with open("eval/golden_questions/starter_set.json", "r") as f:
        questions = json.load(f)

    results = []
    
    print("Running evaluation over", len(questions), "questions...")
    
    for q in questions:
        query_text = q['question']
        in_domain = q['in_domain']
        spans = q.get('answer_spans', [])
        
        # Get embeddings
        emb = create_embedding([query_text])[0]
        
        # Search Top 10
        chunks = search_vectors(emb, top_k=10)
        
        max_sim = chunks[0]['similarity'] if chunks else 0.0
        
        relevant_ranks = []
        for rank, chunk in enumerate(chunks, 1):
            if is_relevant(chunk, spans):
                relevant_ranks.append(rank)
                
        results.append({
            "id": q['id'],
            "in_domain": in_domain,
            "max_sim": max_sim,
            "relevant_ranks": relevant_ranks
        })
        print(f"[{q['id']}] {'IN ' if in_domain else 'OOD'} - Max Sim: {max_sim:.4f} - Relevant ranks: {relevant_ranks}")

    # Compute ranking metrics for in-domain questions
    in_domain_results = [r for r in results if r['in_domain']]
    ood_results = [r for r in results if not r['in_domain']]
    
    recall_at_5 = 0
    recall_at_10 = 0
    mrr_sum = 0.0
    
    for r in in_domain_results:
        ranks = r['relevant_ranks']
        if any(rank <= 5 for rank in ranks):
            recall_at_5 += 1
        if any(rank <= 10 for rank in ranks):
            recall_at_10 += 1
        if ranks:
            mrr_sum += 1.0 / ranks[0]
            
    n_in = len(in_domain_results)
    final_recall_5 = recall_at_5 / n_in if n_in > 0 else 0
    final_recall_10 = recall_at_10 / n_in if n_in > 0 else 0
    final_mrr = mrr_sum / n_in if n_in > 0 else 0
    
    # Threshold calibration
    best_threshold = 0.0
    best_f1 = -1.0
    best_metrics = {}
    
    thresholds = np.linspace(0.0, 1.0, 101)
    for t in thresholds:
        tp = sum(1 for r in ood_results if r['max_sim'] < t) # OOD and abstained
        fn = sum(1 for r in ood_results if r['max_sim'] >= t) # OOD and NOT abstained
        fp = sum(1 for r in in_domain_results if r['max_sim'] < t) # IN and abstained
        tn = sum(1 for r in in_domain_results if r['max_sim'] >= t) # IN and NOT abstained
        
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0
        
        if f1 > best_f1:
            best_f1 = f1
            best_threshold = t
            best_metrics = {
                "abstention_precision": precision,
                "abstention_recall": recall,
                "abstention_f1": f1
            }
            
    print("\n" + "="*40)
    print("EVALUATION RESULTS")
    print("="*40)
    print(f"Recall@5:  {final_recall_5:.4f}")
    print(f"Recall@10: {final_recall_10:.4f}")
    print(f"MRR:       {final_mrr:.4f}")
    print(f"\nAbstention Calibration:")
    print(f"Optimal Threshold: {best_threshold:.4f}")
    print(f"Abstention Precision: {best_metrics['abstention_precision']:.4f}")
    print(f"Abstention Recall:    {best_metrics['abstention_recall']:.4f}")
    print(f"Abstention F1:        {best_metrics['abstention_f1']:.4f}")
    
    # Write updated config
    with open("config.yaml", "r") as f:
        conf = yaml.safe_load(f)
        
    conf['retrieval']['abstention_threshold'] = float(best_threshold)
    
    with open("config.yaml", "w") as f:
        yaml.safe_dump(conf, f, sort_keys=False)
    print("\nUpdated config.yaml with new abstention_threshold.")
    
    # Save baseline
    baseline = {
        "recall_5": final_recall_5,
        "recall_10": final_recall_10,
        "mrr": final_mrr,
        "abstention_threshold": best_threshold,
        "abstention_precision": best_metrics['abstention_precision'],
        "abstention_recall": best_metrics['abstention_recall'],
        "abstention_f1": best_metrics['abstention_f1']
    }
    
    os.makedirs("eval/baselines", exist_ok=True)
    with open("eval/baselines/v0_baseline.json", "w") as f:
        json.dump(baseline, f, indent=2)
    print("Saved baseline to eval/baselines/v0_baseline.json.")

if __name__ == "__main__":
    main()
