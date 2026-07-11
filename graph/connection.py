"""Neo4j Graph Database Connection with environment variable configuration"""
import os
from neo4j import GraphDatabase

# Load configuration from environment with defaults
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "changeme")

# Create driver with connection pooling
driver = GraphDatabase.driver(
    NEO4J_URI,
    auth=(NEO4J_USER, NEO4J_PASSWORD),
    max_connection_lifetime=30 * 60,  # 30 minutes
    max_connection_pool_size=50,
    connection_acquisition_timeout=60,  # 60 seconds
)

def verify_connection() -> bool:
    """Verify Neo4j connection is working"""
    try:
        driver.verify_connectivity()
        return True
    except Exception:
        return False

def close_driver():
    """Close the driver connection"""
    driver.close()

if __name__ == "__main__":
    # Test connection
    if verify_connection():
        print("✓ Neo4j connection successful")
        with driver.session() as session:
            result = session.run("RETURN 'Connection successful' AS msg")
            record = result.single()
            if record:
                print(record["msg"])
    else:
        print("✗ Neo4j connection failed")
        exit(1)
    close_driver()