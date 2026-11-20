import torch
import torch.nn.functional as F
from pathlib import Path
from typing import List, Tuple
from transformers import AutoTokenizer, AutoModel, AutoModelForSequenceClassification
from app.config import settings

class EmbeddingEngine:
    """Bộ sinh Dense Embedding sử dụng model cục bộ multilingual-e5-small (384 dim)."""
    
    def __init__(self, model_path: Path):
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.tokenizer = AutoTokenizer.from_pretrained(str(model_path))
        self.model = AutoModel.from_pretrained(str(model_path)).to(self.device)
        self.model.eval()

    def _mean_pooling(self, model_output, attention_mask):
        token_embeddings = model_output[0]
        input_mask_expanded = attention_mask.unsqueeze(-1).expand(token_embeddings.size()).float()
        return torch.sum(token_embeddings * input_mask_expanded, 1) / torch.clamp(input_mask_expanded.sum(1), min=1e-9)

    def embed_passages(self, texts: List[str]) -> List[List[float]]:
        """Embed danh sách văn bản (prefix 'passage: ' theo quy chuẩn E5)."""
        if not texts:
            return []
        prefixed = [f"passage: {t}" for t in texts]
        return self._embed(prefixed)

    def embed_query(self, query: str) -> List[float]:
        """Embed câu hỏi tìm kiếm (prefix 'query: ' theo quy chuẩn E5)."""
        prefixed = [f"query: {query}"]
        vectors = self._embed(prefixed)
        return vectors[0]

    def _embed(self, texts: List[str]) -> List[List[float]]:
        encoded = self.tokenizer(
            texts,
            max_length=512,
            padding=True,
            truncation=True,
            return_tensors="pt"
        ).to(self.device)
        
        with torch.no_grad():
            outputs = self.model(**encoded)
            embeddings = self._mean_pooling(outputs, encoded["attention_mask"])
            embeddings = F.normalize(embeddings, p=2, dim=1)
            
        return embeddings.cpu().tolist()

class RerankerEngine:
    """Bộ chấm điểm lại (Reranking) sử dụng model cục bộ BAAI/bge-reranker-v2-m3."""
    
    def __init__(self, model_path: Path):
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.tokenizer = AutoTokenizer.from_pretrained(str(model_path))
        self.model = AutoModelForSequenceClassification.from_pretrained(str(model_path)).to(self.device)
        self.model.eval()

    def compute_scores(self, pairs: List[Tuple[str, str]], batch_size: int = 16) -> List[float]:
        """Tính điểm liên quan giữa từng cặp (query, doc_chunk) theo mini-batch tối ưu CPU."""
        if not pairs:
            return []
            
        all_scores = []
        for i in range(0, len(pairs), batch_size):
            batch_pairs = pairs[i:i + batch_size]
            features = self.tokenizer(
                batch_pairs,
                padding=True,
                truncation=True,
                max_length=384,
                return_tensors="pt"
            ).to(self.device)
            
            with torch.no_grad():
                scores = self.model(**features).logits.view(-1).float()
                batch_scores = torch.sigmoid(scores).cpu().tolist()
                if isinstance(batch_scores, list):
                    all_scores.extend(batch_scores)
                else:
                    all_scores.append(batch_scores)
            
        return all_scores
