#!/bin/bash
# Test runner script for FSRsync

set -e  # Exit on error

echo "========================================="
echo "FSRsync Test Suite"
echo "========================================="

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if pytest is available
if ! command -v pytest &> /dev/null; then
    echo -e "${RED}pytest not found. Installing...${NC}"
    pip install -q pytest pytest-asyncio httpx
fi

# Function to run tests
run_tests() {
    local test_type=$1
    local test_args=$2

    echo ""
    echo -e "${YELLOW}Running ${test_type} tests...${NC}"
    echo "========================================="

    if pytest ${test_args}; then
        echo -e "${GREEN}✓ ${test_type} tests passed${NC}"
        return 0
    else
        echo -e "${RED}✗ ${test_type} tests failed${NC}"
        return 1
    fi
}

# Track failures
FAILED=0

# 1. Run unit tests
if run_tests "Unit" "test/ -m 'not integration and not performance' --tb=short"; then
    :
else
    FAILED=1
fi

# 2. Run sync scenario tests
if run_tests "Sync Scenarios" "test/test_sync_scenarios.py --tb=short"; then
    :
else
    FAILED=1
fi

# 3. Run filesystem monitor tests
if run_tests "Filesystem Monitor" "test/test_filesystem_monitor.py --tb=short"; then
    :
else
    FAILED=1
fi

# 4. Run web API tests
if run_tests "Web API" "test/test_web_api.py --tb=short"; then
    :
else
    FAILED=1
fi

# 5. Run rsync manager tests
if run_tests "Rsync Manager" "test/test_rsync_manager.py --tb=short"; then
    :
else
    FAILED=1
fi

# 6. Run integration tests (if in Docker)
if [ -f "/.dockerenv" ] || [ -d "/root/source" ]; then
    echo ""
    echo -e "${YELLOW}Docker environment detected, running integration tests...${NC}"
    if run_tests "Integration" "test/test_docker_sync.py -m integration --tb=short"; then
        :
    else
        FAILED=1
    fi
else
    echo ""
    echo -e "${YELLOW}Not in Docker environment, skipping integration tests${NC}"
fi

# 7. Run performance tests (optional)
if [ "$RUN_PERF_TESTS" = "true" ]; then
    if run_tests "Performance" "test/ -m performance --tb=short"; then
        :
    else
        FAILED=1
    fi
else
    echo ""
    echo -e "${YELLOW}Skipping performance tests (set RUN_PERF_TESTS=true to run)${NC}"
fi

echo ""
echo "========================================="
if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}All tests passed! ✓${NC}"
    exit 0
else
    echo -e "${RED}Some tests failed! ✗${NC}"
    exit 1
fi
