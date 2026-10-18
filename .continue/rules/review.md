---
invokable: true
---

Review this code for potential issues, including:

1. **Security Vulnerabilities**:
   - Check for hardcoded secrets (API keys, passwords) in code or config files.
   - Ensure proper authentication and authorization checks on all API endpoints.
   - Validate input sanitization to prevent injection attacks (SQL, Cypher, etc.).
   - Review JWT implementation for proper secret strength and expiration.

2. **Performance Issues**:
   - Look for N+1 query problems in Neo4j or PostgreSQL interactions.
   - Check for inefficient data fetching in frontend (waterfall requests).
   - Review GNN model inference for potential bottlenecks.
   - Validate caching strategies are appropriately used.

3. **Code Quality & Maintainability**:
   - Ensure consistent error handling and logging.
   - Check for proper use of TypeScript types in frontend.
   - Review Python code for adherence to PEP8 and project conventions.
   - Verify that lazy imports are correctly implemented for heavy ML dependencies.

4. **Scalability Concerns**:
   - Review multi-tenancy implementation for proper data isolation.
   - Check that background tasks (like GNN retraining) don't block API requests.
   - Validate that database connections are properly pooled.
   - Review frontend bundle size and lazy loading strategies.

5. **Testing Coverage**:
   - Ensure critical paths have unit and integration tests.
   - Check for test files corresponding to new features.
   - Validate that health checks cover all critical services.

6. **Deployment & Configuration**:
   - Verify docker-compose.yml matches required services.
   - Check that .env.example contains all necessary variables.
   - Review Makefile commands for correctness and completeness.
   - Ensure environment-specific configurations are handled properly.

Provide specific, actionable feedback for improvements.