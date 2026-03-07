"""Azure AI Search service integration."""
import json
from azure.search.documents import SearchClient
from azure.core.credentials import AzureKeyCredential
from shared.config.settings import settings
from shared.utils.logging import get_logger
from typing import List, Dict, Optional
from AI.src.services.azure_openai_service import AzureOpenAIService
from shared.models.job_cluster_metrics import JobClusterMetrics

logger = get_logger(__name__)


class AzureSearchService:
    """Service for Azure AI Search integration."""
    
    def __init__(self):
        """Initialize Azure AI Search service."""
        # Check if Azure AI Search is configured
        if not settings.azure_search_endpoint or not settings.azure_search_api_key:
            logger.warning("azure_search_not_configured")
            self.client = None
            self.openai_service = AzureOpenAIService()
            return

        index_name = settings.azure_search_index_name or "recommendations-index"
        try:
            self.client = SearchClient(
                endpoint=settings.azure_search_endpoint,
                index_name=index_name,
                credential=AzureKeyCredential(settings.azure_search_api_key)
            )
            self.openai_service = AzureOpenAIService()
            logger.info("azure_search_service_initialized")
        except Exception as e:
            logger.warning("azure_search_init_failed", error=str(e))
            self.client = None
            self.openai_service = AzureOpenAIService()
    
    def index_recommendation(self, recommendation: dict) -> bool:
        """Index a recommendation for semantic search.
        
        Args:
            recommendation: Recommendation dictionary to index
            
        Returns:
            True if successful, False otherwise
        """
        if not self.client:
            logger.warning("azure_search_not_available_skipping_index")
            return False
        
        try:
            # Generate embedding from rationale and explanation
            rationale = recommendation.get('rationale', '')
            explanation = recommendation.get('detailed_explanation', '')
            text = f"{rationale} {explanation}".strip()
            
            if not text:
                logger.warning("empty_recommendation_text", recommendation_id=recommendation.get("recommendation_id"))
                return False
            
            embedding = self.openai_service.get_embeddings().embed_query(text)
            
            document = {
                "id": recommendation.get("recommendation_id", f"rec-{recommendation.get('job_id', 'unknown')}"),
                "job_id": recommendation.get("job_id", ""),
                "workload_type": recommendation.get("workload_type", ""),
                "content": text,
                "embedding": embedding,
                "document_type": "recommendation",
                "is_recommendation": True,
                "config_quality": "pending",  # Initially pending, updated after validation
                "recommendation": json.dumps(recommendation) if isinstance(recommendation, dict) else str(recommendation),
            }
            
            self.client.upload_documents(documents=[document])
            logger.info("indexed_recommendation", recommendation_id=recommendation.get("recommendation_id"))
            return True
        except Exception as e:
            logger.error("index_recommendation_error", error=str(e))
            return False
    
    def search_similar(
        self, 
        query: str, 
        top_k: int = 5,
        filter_quality: bool = True
    ) -> List[Dict]:
        """Search for similar recommendations.
        
        Args:
            query: Search query text
            top_k: Number of results to return
            filter_quality: If True, only return recommendations with config_quality="optimal"
            
        Returns:
            List of similar recommendations
        """
        if not self.client:
            logger.warning("azure_search_not_available_skipping_search")
            return []
        
        try:
            # Generate query embedding
            query_embedding = self.openai_service.get_embeddings().embed_query(query)
            
            # Build search options
            search_options = {
                "vector_queries": [{
                    "vector": query_embedding,
                    "k_nearest_neighbors": top_k,
                    "fields": "embedding"
                }]
            }
            
            # Filter by quality if requested
            if filter_quality:
                search_options["filter"] = "config_quality eq 'optimal' and is_recommendation eq true"
            else:
                search_options["filter"] = "is_recommendation eq true"
            
            # Vector search
            results = self.client.search(
                search_text="",
                **search_options
            )
            
            recommendations = [result for result in results]
            logger.info("search_similar_complete", query=query[:100], results_count=len(recommendations), filter_quality=filter_quality)
            return recommendations
        except Exception as e:
            logger.error("search_similar_error", error=str(e))
            return []
    
    def index_job_cluster_metrics(self, metrics: JobClusterMetrics) -> bool:
        """Index raw job cluster metrics for pattern matching.
        
        Indexes utilization patterns and workload characteristics.
        Does NOT treat current config as recommendation.
        
        Args:
            metrics: JobClusterMetrics object to index
            
        Returns:
            True if successful, False otherwise
        """
        if not self.client:
            logger.warning("azure_search_not_available_skipping_index")
            return False
        
        try:
            # Build searchable text from utilization patterns (not configs)
            text = f"""
            WORKLOAD PATTERN (for similarity matching only):
            Workload Type: {metrics.workload_type or 'Unknown'}
            CPU Utilization: {metrics.avg_cpu_utilization_pct}% average, {metrics.peak_cpu_utilization_pct}% peak
            Memory Utilization: {metrics.avg_memory_utilization_pct}% average, {metrics.peak_memory_utilization_pct}% peak
            Node Consumption: {metrics.avg_nodes_consumed} average, {metrics.p95_nodes_consumed} p95, {metrics.p99_nodes_consumed} p99
            Job Duration: {metrics.job_duration_seconds} seconds
            Task Count: {metrics.task_count}
            Parallelism Ratio: {metrics.parallelism_ratio}
            
            CURRENT CONFIGURATION (for reference only, may not be optimal):
            Node Type: {metrics.current_node_type}
            Workers: {metrics.current_min_workers}-{metrics.current_max_workers}
            
            NOTE: This configuration is what was used, not necessarily what should be used.
            Use this for pattern matching only. Optimization should be based on utilization patterns.
            """
            
            # Generate embedding
            embedding = self.openai_service.get_embeddings().embed_query(text)
            
            metrics_dict = {
                "avg_cpu_utilization_pct": metrics.avg_cpu_utilization_pct,
                "avg_memory_utilization_pct": metrics.avg_memory_utilization_pct,
                "peak_cpu_utilization_pct": metrics.peak_cpu_utilization_pct,
                "peak_memory_utilization_pct": metrics.peak_memory_utilization_pct,
                "avg_nodes_consumed": metrics.avg_nodes_consumed,
                "p95_nodes_consumed": metrics.p95_nodes_consumed,
                "p99_nodes_consumed": metrics.p99_nodes_consumed,
                "job_duration_seconds": metrics.job_duration_seconds,
                "task_count": metrics.task_count,
                "parallelism_ratio": metrics.parallelism_ratio
            }
            current_config_dict = {
                "node_type": metrics.current_node_type,
                "min_workers": metrics.current_min_workers,
                "max_workers": metrics.current_max_workers
            }
            document = {
                "id": f"metrics-{metrics.job_id}-{metrics.job_run_id}",
                "job_id": metrics.job_id,
                "job_run_id": metrics.job_run_id,
                "workspace_id": metrics.workspace_id,
                "workload_type": metrics.workload_type or "Unknown",
                "content": text,
                "embedding": embedding,
                "document_type": "job_cluster_metrics",
                "is_recommendation": False,
                "config_quality": "unknown",
                "metrics": json.dumps(metrics_dict),
                "current_config": json.dumps(current_config_dict),
            }
            
            self.client.upload_documents(documents=[document])
            logger.info("indexed_job_cluster_metrics", job_id=metrics.job_id, job_run_id=metrics.job_run_id)
            return True
        except Exception as e:
            logger.error("index_job_cluster_metrics_error", error=str(e))
            return False
    
    def search_similar_jobs(
        self, 
        job_cluster_metrics: dict, 
        top_k: int = 5,
        filter_recommendations: bool = False
    ) -> List[Dict]:
        """Search for similar jobs based on utilization patterns.
        
        Args:
            job_cluster_metrics: Dictionary with job cluster metrics (from aggregated metrics)
            top_k: Number of results to return
            filter_recommendations: If True, only return jobs that have recommendations
            
        Returns:
            List of similar job documents
        """
        if not self.client:
            logger.warning("azure_search_not_available_skipping_search")
            return []
        
        try:
            # Build query from utilization patterns (not configs)
            workload_type = job_cluster_metrics.get("workload_type", job_cluster_metrics.get("current_workload_type", "Unknown"))
            avg_cpu = job_cluster_metrics.get("avg_cpu_utilization", job_cluster_metrics.get("avg_cpu_utilization_pct", 0))
            avg_memory = job_cluster_metrics.get("avg_memory_utilization", job_cluster_metrics.get("avg_memory_utilization_pct", 0))
            avg_nodes = job_cluster_metrics.get("avg_nodes_consumed", job_cluster_metrics.get("p95_nodes_consumed", 0))
            
            query = f"""
            Workload Type: {workload_type}
            CPU Utilization: {avg_cpu}% average
            Memory Utilization: {avg_memory}% average
            Node Consumption: {avg_nodes} average
            """
            
            # Generate query embedding
            query_embedding = self.openai_service.get_embeddings().embed_query(query)
            
            # Build search options
            search_options = {
                "vector_queries": [{
                    "vector": query_embedding,
                    "k_nearest_neighbors": top_k,
                    "fields": "embedding"
                }]
            }
            
            # Filter by document type if needed
            if filter_recommendations:
                search_options["filter"] = "is_recommendation eq true"
            else:
                # Prefer job_cluster_metrics documents for pattern matching
                search_options["filter"] = "document_type eq 'job_cluster_metrics'"
            
            # Vector search
            results = self.client.search(
                search_text="",
                **search_options
            )
            
            jobs = [result for result in results]
            logger.info("search_similar_jobs_complete", query=query[:100], results_count=len(jobs))
            return jobs
        except Exception as e:
            logger.error("search_similar_jobs_error", error=str(e))
            return []
    
    def link_recommendation_to_job(
        self, 
        recommendation_id: str, 
        job_id: str
    ) -> bool:
        """Link a recommendation to its source job metrics.
        
        Args:
            recommendation_id: ID of the recommendation
            job_id: ID of the job it was generated for
            
        Returns:
            True if successful, False otherwise
        """
        if not self.client:
            logger.warning("azure_search_not_available_skipping_link")
            return False
        
        try:
            # Search for job metrics documents
            results = self.client.search(
                search_text=f"job_id eq '{job_id}'",
                filter="document_type eq 'job_cluster_metrics'"
            )
            
            # Update job metrics documents to reference recommendation
            for result in results:
                doc_id = result.get("id")
                if doc_id:
                    # Update document with recommendation link
                    update_doc = {
                        "id": doc_id,
                        "recommendation_id": recommendation_id
                    }
                    self.client.upload_documents(documents=[update_doc])
            
            logger.info("linked_recommendation_to_job", recommendation_id=recommendation_id, job_id=job_id)
            return True
        except Exception as e:
            logger.error("link_recommendation_error", error=str(e))
            return False
    
    def update_recommendation_quality(
        self,
        recommendation_id: str,
        config_quality: str,
        feedback_data: Optional[dict] = None
    ) -> bool:
        """Update the quality status of an existing recommendation.
        
        Uses Azure AI Search's 'merge' action to update only the quality field
        without regenerating embeddings. This is efficient and preserves the
        original searchable content.
        
        Args:
            recommendation_id: ID of the recommendation to update
            config_quality: New quality status ("optimal", "suboptimal", or "failed")
            feedback_data: Optional feedback data (actual savings, performance impact, etc.)
            
        Returns:
            True if successful, False otherwise
        """
        if not self.client:
            logger.warning("azure_search_not_available_skipping_update")
            return False
        
        if config_quality not in ["optimal", "suboptimal", "failed", "pending"]:
            logger.error("invalid_config_quality", quality=config_quality)
            return False
        
        try:
            from datetime import datetime
            
            # Build update document using merge action
            update_doc = {
                "@search.action": "merge",  # Partial update, not full replace
                "id": recommendation_id,
                "config_quality": config_quality
            }
            
            # Add feedback data if provided
            if feedback_data:
                update_doc["feedback"] = feedback_data
                update_doc["updated_at"] = datetime.utcnow().isoformat()
            
            self.client.upload_documents(documents=[update_doc])
            logger.info(
                "updated_recommendation_quality",
                recommendation_id=recommendation_id,
                quality=config_quality
            )
            return True
        except Exception as e:
            logger.error("update_quality_error", recommendation_id=recommendation_id, error=str(e))
            return False

