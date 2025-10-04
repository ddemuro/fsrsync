#!/bin/bash
# This script is used to create a sandbox environment for testing purposes

function build() {
    echo "Building the application..."
    # Build the server image
    docker compose build server
    # Build the client image
    docker compose build client
}

function run() {
    echo "Running the application..."
    # Run docker compose up server
    docker compose up -d server
    # Run docker compose up client
    docker compose up -d client
}

function test() {
    SUCCESS="0"
    echo "Running tests... for $1"

    # Run unit tests first
    echo "Running unit tests with pytest..."
    if command -v pytest &> /dev/null; then
        pytest test/ -v || {
            echo "Unit tests failed!"
            SUCCESS="$SUCCESS,1"
        }
    else
        echo "pytest not found, skipping unit tests"
    fi

    echo "Starting the client to receive files from the server..."
    export OPERATION="server"
    docker compose build server
    export OPERATION="$1"
    docker compose build client

    # Cleanup the test directories
    rm -rf test/destination/*
    mkdir -p test/destination

    # Run the client
    docker compose up client &disown
    echo "Wait for 20 seconds for the client to start..."
    sleep 20
    echo "Starting the server to send files to the client..."
    # Run the server
    docker compose up server &disown
    sleep 20

    #
    # Test adding a file to source, should trigger a send to client
    #
    echo "Testing adding a file to source, should trigger a send to client..."
    # Add a file to the source directory
    echo "Hello, World!" > test/source/test
    # Check if file exists in the client directory
    if [ -f "test/destination/test" ]; then
        echo "File was successfully sent to the client!"
        SUCCESS="$SUCCESS,0"
    else
        echo "File was not sent to the client!"
        SUCCESS="$SUCCESS,1"
    fi

    #
    # Test removing a file from source, should trigger a delete on client
    #
    echo "Testing removing a file from source, should trigger a delete on client..."
    # Remove the file from the source directory
    rm test/destination/test
    # Check if file exists in the client directory
    if [ ! -f "test/destination/test" ]; then
        echo "File was successfully deleted from the client!"
        SUCCESS="$SUCCESS,0"
    else
        echo "File was not deleted from the client!"
        SUCCESS="$SUCCESS,1"
    fi

    # Check if all tests passed using grep on the SUCCESS variable
    ENDRES=0
    if echo $SUCCESS | grep -q "1"; then
        echo "Tests failed!"
        ENDRES=1
    else
        echo "All tests passed!"
    fi

    #
    # Stop the server and client
    #
    echo "Stopping the server and client..."
    # Stop the server and client
    docker compose down
    # rm -rf test/destination/source
    exit $ENDRES
}

function exec() {
    echo "Executing terminal... pick if you want to exec into server or client ./sandbox.sh exec [server/client]"
    # Check if $2 is server or client
    if [ $2 == "server" ]; then
        docker exec -it server /bin/bash
    elif [ $2 == "client" ]; then
        docker exec -it client /bin/bash
    else
        echo "Please specify either 'server' or 'client' as a parameter."
        exit 1
    fi
}

# Quick retest
function qrt() {
    docker compose build server
    echo "Running tests..."
    echo "Starting the client to receive files from the server..."
    # Run the client
    docker compose up -d client
    sleep 3
    docker compose up server &disown
    sleep 5
    rm test/source/test.txt
    touch test/source/test.txt
    docker compose down server
}

# Run unit tests in Docker
function test_unit() {
    echo "Running unit tests in Docker..."
    docker compose -f docker-compose.test.yml build test-server
    docker compose -f docker-compose.test.yml run --rm test-server
    EXIT_CODE=$?
    docker compose -f docker-compose.test.yml down
    return $EXIT_CODE
}

# Run performance tests
function test_perf() {
    echo "Running performance tests in Docker..."
    docker compose -f docker-compose.test.yml build perf-test
    docker compose -f docker-compose.test.yml run --rm perf-test
    EXIT_CODE=$?
    docker compose -f docker-compose.test.yml down
    return $EXIT_CODE
}

# Run all tests (unit + integration)
function test_all() {
    echo "Running all tests..."

    # Run unit tests
    echo "=== Unit Tests ==="
    test_unit
    UNIT_EXIT=$?

    # Run integration tests
    echo "=== Integration Tests ==="
    test sync
    INTEGRATION_EXIT=$?

    # Run performance tests
    echo "=== Performance Tests ==="
    test_perf
    PERF_EXIT=$?

    # Summary
    echo ""
    echo "========================================="
    echo "Test Summary:"
    echo "  Unit Tests: $([ $UNIT_EXIT -eq 0 ] && echo 'PASSED' || echo 'FAILED')"
    echo "  Integration Tests: $([ $INTEGRATION_EXIT -eq 0 ] && echo 'PASSED' || echo 'FAILED')"
    echo "  Performance Tests: $([ $PERF_EXIT -eq 0 ] && echo 'PASSED' || echo 'FAILED')"
    echo "========================================="

    if [ $UNIT_EXIT -eq 0 ] && [ $INTEGRATION_EXIT -eq 0 ] && [ $PERF_EXIT -eq 0 ]; then
        echo "All tests PASSED! ✓"
        return 0
    else
        echo "Some tests FAILED! ✗"
        return 1
    fi
}

# Check for arguments
echo "Args: 1: $1, 2: $2, 3: $3, 4: $4"
while [[ $# -gt 0 ]]; do
    case $1 in
        build)
            build
            ;;
        run)
            run
            ;;
        test)
            # If $2 is fullsync, run fullsync test
            if [ "$2" == "fullsync" ]; then
                echo "Running fullsync test..."
                test fullsync
                exit 0
            fi
            # Otherwise, run normal test
            test sync
            ;;
        testbuild)
            build
            test
            ;;
        exec)
            exec $2
            ;;
        qrt)
            qrt
            ;;
        test-unit)
            test_unit
            ;;
        test-perf)
            test_perf
            ;;
        test-all)
            test_all
            ;;
        *)
            echo "Error: Valid arguments are: 'run', 'test', 'build', 'exec', 'qrt', 'test-unit', 'test-perf', 'test-all'"
            exit 1
            ;;
    esac
    shift # Shift to the next argument
done
