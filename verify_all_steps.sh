#!/bin/bash

# Verification script for Steps 1-4 fixes
# Run this on your machine where the gateway is accessible

BASE_URL="http://localhost:8001"

echo "========================================================================"
echo "🔍 SANITY CHECKS - Verify All 4 Steps Work"
echo "========================================================================"

# Helper function to run Cypher query
run_query() {
    local query=$1
    local description=$2
    echo ""
    echo "✅ $description"
    curl -s -X POST "$BASE_URL/api/query/execute" \
      -H "Content-Type: application/json" \
      -d "{\"query\": \"$query\"}" | python3 -m json.tool 2>/dev/null || echo "Query failed"
}

# TEST 1: Package nodes exist
run_query "MATCH (p:Package) RETURN count(p) as package_count" \
    "TEST 1: Package Nodes Created"

# TEST 2: File nodes with both path AND name properties (STEP 1 FIX)
run_query "MATCH (f:File) WHERE f.path IS NOT NULL AND f.name IS NOT NULL RETURN count(f) as files_with_both_properties" \
    "TEST 2: File Nodes Have 'path' AND 'name' Properties (STEP 1)"

# TEST 3: CONTAINS relationships (STEP 2 FIX)
run_query "MATCH (p:Package)-[:CONTAINS]->(f:File) RETURN count(*) as contains_relationships" \
    "TEST 3: CONTAINS Relationships (Package → File) - STEP 2"

# TEST 3B: Sample CONTAINS relationships
run_query "MATCH (p:Package)-[:CONTAINS]->(f:File) RETURN p.name as package, f.path as file LIMIT 5" \
    "TEST 3B: Sample CONTAINS Relationships"

# TEST 4: Package names (STEP 3 FIX)
run_query "MATCH (p:Package) RETURN p.name as package_name LIMIT 10" \
    "TEST 4: Package Names (STEP 3 - Normalization)"

# TEST 5: Class and Function nodes
run_query "MATCH (c:Class) RETURN count(c) as class_count" \
    "TEST 5A: Class Nodes Created"

run_query "MATCH (f:Function) RETURN count(f) as function_count" \
    "TEST 5B: Function Nodes Created"

# TEST 6: DEFINES relationships
run_query "MATCH (f:File)-[:DEFINES]->(e) RETURN count(*) as defines_relationships" \
    "TEST 6: DEFINES Relationships (File → Class/Function)"

# TEST 7: Sample graph structure
run_query "MATCH (p:Package)-[:CONTAINS]->(f:File)-[:DEFINES]->(c:Class) RETURN p.name as pkg, f.path as file, c.name as class LIMIT 3" \
    "TEST 7: Sample Complete Graph Structure (Package → File → Class)"

echo ""
echo "========================================================================"
echo "✅ VERIFICATION COMPLETE"
echo "========================================================================"