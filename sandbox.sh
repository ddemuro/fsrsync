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
    echo "Running tests..."
    echo "Starting the client to receive files from the server..."
    OPERATION=client docker compose build server
    OPERATION=sync docker compose build client
    # Run the client
    docker compose up -d client
    echo "Wait for 5 seconds for the client to start..."
    sleep 5
    echo "Starting the server to send files to the client..."
    # Run the server
    docker compose up server &disown
    sleep 5

    #
    # Test adding a file to source, should trigger a send to client
    #
    echo "Testing adding a file to source, should trigger a send to client..."
    # Add a file to the source directory
    echo "Hello, World!" > test/source/test.txt
    # Check if file exists in the client directory
    if [ -f "test/destination/test.txt" ]; then
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
    rm test/source/test.txt
    # Check if file exists in the client directory
    if [ ! -f "test/destination/test.txt" ]; then
        echo "File was successfully deleted from the client!"
        SUCCESS="$SUCCESS,0"
    else
        echo "File was not deleted from the client!"
        SUCCESS="$SUCCESS,1"
    fi

    # Check if all tests passed using grep on the SUCCESS variable
    if echo $SUCCESS | grep -q "1"; then
        echo "Tests failed!"
    else
        echo "All tests passed!"
    fi

    #
    # Stop the server and client
    #
    echo "Stopping the server and client..."
    # Stop the server and client
    docker compose down
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

# Check for arguments
while $1; do
    case $o in
        build)
            build
            ;;
        run)
            run
            ;;
        test)
            test
            ;;
        exec)
            exec $2
            ;;
        qrt)
            qrt
            ;;
        \?)
            echo "Only 'run, test, build' are valid arguments."
            exit 1
            ;;
    esac
done

# If no arguments are provided, print error message and exit
echo "Error: Please specify either 'run' or 'test' as a parameter."
exit 1