"""FASE 5 — pacote do servidor MCP de busca RAG.

Contem apenas `rag_server.py` (tool rag_search). Mantido como pacote para que
`python -m mcpsrv.rag_server` funcione a partir da raiz do repo.

Chama-se `mcpsrv` (nao `mcp`) para NAO colidir com o pacote instalado do SDK
oficial `mcp` — era preciso um workaround de loader explicito enquanto o
diretorio se chamava `mcp` (BUG-008, resolvido em S25/T-ENV-4).
"""
