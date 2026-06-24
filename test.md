Structuring this in a modular, phased approach is the exact right strategy. To ensure Phase 1 smoothly transitions into an API (Phase 2), a UI (Phase 3), and an automated Azure DevOps pipeline (Phase 4), we must treat the agent not as a loose notebook script, but as a **governed Python package**.
In Phase 1, we will isolate the core LangChain reasoning loop, define its data tools, and register it directly to the **Unity Catalog** via MLflow. Once registered, Databricks turns this agent into a scalable, serverless endpoint—which is exactly what your future FastAPI layer will query.
## Phase 1: Code Architecture & Directory Structure
To make this repository fully compatible with Azure DevOps pipelines later, we must establish a clean, production-grade project layout.
```text
cluster-metrics-agent/
├── config/
│   └── external_endpoint.json    # Azure AI Foundry proxy configuration
├── src/
│   ├── __init__.py
│   ├── tools.py                  # LangChain tools for pulling Delta metrics
│   └── agent.py                  # LangChain agent definition & chain logic
├── register_agent.py             # Script executed by developer (or CI/CD later)
└── requirements.txt              # Standard dependencies

```
### 1. Define Dependencies (requirements.txt)
```text
databricks-sdk>=0.28.0
mlflow>=2.14.0
langchain>=0.2.0
langchain-community>=0.2.0
langchain-openai>=0.1.0
pandas>=2.0.0

```
## Phase 1: Implementation Details
### Step 1: External Model Endpoint Configuration
Before writing the agent, we define the external proxy to Azure AI Foundry. This lives in your Databricks Workspace under Model Serving.
**config/external_endpoint.json**
```json
{
  "name": "foundry-llm-proxy",
  "config": {
    "served_entities": [
      {
        "name": "azure-foundry-model",
        "external_model": {
          "name": "gpt-4o",
          "provider": "openai",
          "openai_config": {
            "openai_api_type": "azure",
            "openai_api_base": "https://your-foundry-resource.openai.azure.com/",
            "openai_api_version": "2024-02-15-preview",
            "openai_api_key": "{{secrets/telemetry_scope/foundry_key}}"
          }
        }
      }
    ]
  }
}

```
> *Phase 4 Future-Proofing:* In Phase 4, your Azure DevOps pipeline will use the Databricks CLI to apply this JSON configuration automatically across Dev, QA, and Prod environments.
> 
### Step 2: Build the Data Tools (src/tools.py)
This file houses the exact mechanisms the agent uses to fetch cluster data. By wrapping these in standard Python functions with explicit docstrings, LangChain can natively parse them as executable tools.
```python
from langchain.tools import tool
from pyspark.sql import SparkSession
import pandas as pd

@tool
def fetch_cluster_metrics(cluster_id: str, lookback_hours: int = 24) -> str:
    """
    Queries the Delta lake for a specific Databricks cluster's CPU, Memory, 
    and execution telemetry over a designated lookback window.
    Returns a string representation of a summarized Pandas DataFrame.
    """
    # Grab the active Spark session natively inside the execution context
    spark = SparkSession.builder.getOrCreate()
    
    query = f"""
        SELECT timestamp, cpu_utilization, memory_utilization, active_tasks, queued_tasks
        FROM main.telemetry.job_cluster_metrics
        WHERE cluster_id = '{cluster_id}'
          AND timestamp >= current_timestamp() - INTERVAL {lookback_hours} HOURS
        ORDER BY timestamp DESC
    """
    
    try:
        df = spark.sql(query).toPandas()
        if df.empty:
            return f"No metrics found for cluster {cluster_id} in the last {lookback_hours} hours."
        
        # Calculate summary metrics to minimize token usage
        summary = {
            "p95_cpu": df["cpu_utilization"].quantile(0.95),
            "avg_mem": df["memory_utilization"].mean(),
            "max_queued_tasks": df["queued_tasks"].max(),
            "total_rows_analyzed": len(df)
        }
        return f"Cluster Data Summary for {cluster_id}: {summary}"
    except Exception as e:
        return f"Error querying Delta table: {str(e)}"

```
### Step 3: Define the LangChain Agent Logic (src/agent.py)
Here we initialize the model via the Databricks model-serving ecosystem and bind our data-fetching tool to it.
```python
from langchain_openai import ChatDatabricks
from langchain.agents import AgentExecutor, create_openai_tools_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from src.tools import fetch_cluster_metrics

def get_metrics_agent_executor():
    # Connect directly to our managed Databricks proxy endpoint
    llm = ChatDatabricks(
        endpoint="foundry-llm-proxy",
        temperature=0.1
    )
    
    tools = [fetch_cluster_metrics]
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are an expert Data Platform Optimization Agent. "
                   "Analyze the provided cluster metrics tool outputs. "
                   "Provide clear recommendations on whether to scale up, scale down, "
                   "or enable autoscaling based on bottlenecks or underutilization."),
        MessagesPlaceholder(variable_name="chat_history", optional=True),
        ("human", "{input}"),
        MessagesPlaceholder(variable_name="agent_scratchpad"),
    ])
    
    agent = create_openai_tools_agent(llm, tools, prompt)
    return AgentExecutor(agent=agent, tools=tools, verbose=True)

```
### Step 4: Register & Deploy to Unity Catalog (register_agent.py)
This is the execution script for Phase 1. It configures MLflow to talk to Unity Catalog, activates **MLflow Tracing**, and logs your LangChain pipeline as a fully deployable model asset.
```python
import mlflow
from src.agent import get_metrics_agent_executor

# Force MLflow to point to Unity Catalog rather than the legacy workspace registry
mlflow.set_registry_uri("databricks-uc")

# Enable automatic deep tracing of LangChain components
mlflow.langchain.autolog(log_models=False)

CATALOG = "main"
SCHEMA = "telemetry"
MODEL_NAME = "cluster_analysis_agent"
FULL_MODEL_PATH = f"{CATALOG}.{SCHEMA}.{MODEL_NAME}"

print("Initializing LangChain Agent...")
agent_pipeline = get_metrics_agent_executor()

print("Logging agent to MLflow and Unity Catalog...")
with mlflow.start_run() as run:
    # Log the model using the native LangChain flavor
    model_info = mlflow.langchain.log_model(
        lc_model=agent_pipeline,
        artifact_path="agent",
        registered_model_name=FULL_MODEL_PATH,
        input_example={"input": "Analyze cluster job-45612 for the last 12 hours."}
    )
    print(f"Agent successfully registered to Unity Catalog: {FULL_MODEL_PATH}")

```
## How This Design Seamlessly Feeds Future Phases
By completing Phase 1 this way, you have already solved the core integration challenges for your next steps:
### Preparing for Phase 2 (FastAPI) & Phase 3 (UI)
When you register the model to Unity Catalog in Phase 1, you can instantly serve it via a **Mosaic AI Model Serving Endpoint** with one click or a single API call.
 * Your FastAPI application (Phase 2) will not need to load the LangChain library, import code, or connect to Spark. It simply makes a standard, lightweight HTTP POST request directly to the serving endpoint.
 * Your UI (Phase 3) talks exclusively to your FastAPI wrapper, keeping the browser entirely separated from data processing details.
### Preparing for Phase 4 (CI/CD via Azure DevOps)
Because all your code lives in clean Python modules (src/), your Phase 4 build pipelines become straightforward:
 1. **Pull Request Validation:** Run standard python linters (flake8, black) and unit tests against your data aggregation logic in tools.py.
 2. **Deployment Pipeline:** The Azure DevOps release pipeline will utilize **Databricks Asset Bundles (DABs)** or the Databricks CLI to execute register_agent.py automatically across your Dev, QA, and Production workspaces, changing the target catalog variables dynamically based on the stage.
