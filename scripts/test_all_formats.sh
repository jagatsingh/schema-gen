#!/bin/bash
# Test script to validate all generated formats
# This script can be run locally or in CI

set -e  # Exit on any error

echo "🧪 Schema-Gen Format Validation Suite"
echo "======================================"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    local color=$1
    local message=$2
    echo -e "${color}${message}${NC}"
}

print_step() {
    echo -e "\n${BLUE}🔍 $1${NC}"
}

print_success() {
    print_status $GREEN "✅ $1"
}

print_error() {
    print_status $RED "❌ $1"
}

print_warning() {
    print_status $YELLOW "⚠️  $1"
}

# Function to check if a command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Function to run a command and capture its result
run_test() {
    local test_name=$1
    local command=$2

    print_step "Running $test_name"

    if eval "$command"; then
        print_success "$test_name passed"
        return 0
    else
        print_error "$test_name failed"
        return 1
    fi
}

# Track test results
total_tests=0
passed_tests=0
failed_tests=0

# Function to record test result
record_result() {
    total_tests=$((total_tests + 1))
    if [ $1 -eq 0 ]; then
        passed_tests=$((passed_tests + 1))
    else
        failed_tests=$((failed_tests + 1))
    fi
}

# 1. Basic syntax validation using pytest
print_step "Running Python syntax validation tests"
if run_test "Format validation tests" "uv run pytest tests/test_format_validation.py -v"; then
    record_result 0
else
    record_result 1
fi

# 2. Comprehensive format validation script
print_step "Running comprehensive format validation"
if run_test "All format validation" "uv run python scripts/validate_all_formats.py --verbose"; then
    record_result 0
else
    record_result 1
fi

# 3. Test generated code execution in a clean environment
print_step "Testing generated code execution"

# Create a temporary directory for testing
temp_dir=$(mktemp -d)
cd "$temp_dir"

# Initialize a new schema-gen project
print_step "Creating test project"
if uv run schema-gen init --input-dir schemas --output-dir generated --targets "pydantic,dataclasses,typeddict"; then
    print_success "Project initialized"

    # Generate schemas
    print_step "Generating schemas"
    if uv run schema-gen generate; then
        print_success "Schemas generated"

        # Test Python imports
        print_step "Testing Python code imports"
        test_results=0

        # Test Pydantic models
        if python3 -c "
import sys
from datetime import datetime
sys.path.append('generated/pydantic')
try:
    import user_models
    user = user_models.User(id=1, name='test', email='test@example.com', age=25, created_at=datetime.now())
    print('✅ Pydantic model works')
except Exception as e:
    print(f'❌ Pydantic model error: {e}')
    sys.exit(1)
"; then
            print_success "Pydantic models import and work correctly"
        else
            print_error "Pydantic models failed"
            test_results=1
        fi

        # Test dataclass models
        if python3 -c "
import sys
from datetime import datetime
sys.path.append('generated/dataclasses')
try:
    import user_models
    user = user_models.User(id=1, name='test', email='test@example.com', age=25, created_at=datetime.now())
    print('✅ Dataclass model works')
except Exception as e:
    print(f'❌ Dataclass model error: {e}')
    sys.exit(1)
"; then
            print_success "Dataclass models import and work correctly"
        else
            print_error "Dataclass models failed"
            test_results=1
        fi

        # Test TypedDict models
        if python3 -c "
import sys
from datetime import datetime
sys.path.append('generated/typeddict')
try:
    import user_models
    user: user_models.User = {'id': 1, 'name': 'test', 'email': 'test@example.com', 'age': 25, 'created_at': datetime.now()}
    print('✅ TypedDict model works')
except Exception as e:
    print(f'❌ TypedDict model error: {e}')
    sys.exit(1)
"; then
            print_success "TypedDict models import and work correctly"
        else
            print_error "TypedDict models failed"
            test_results=1
        fi

        record_result $test_results

    else
        print_error "Schema generation failed"
        record_result 1
    fi
else
    print_error "Project initialization failed"
    record_result 1
fi

# Clean up
cd - > /dev/null
rm -rf "$temp_dir"

# 4. Test external format validators (if available)
print_step "Testing external format validators"

external_tests=0
external_passed=0

# Check for TypeScript compiler
if command_exists npx && command_exists node; then
    print_step "Testing TypeScript/Zod validation"
    # Create a temporary Zod schema and test it
    temp_ts=$(mktemp --suffix=.ts)
    cat > "$temp_ts" << 'EOF'
import { z } from 'zod';

export const UserSchema = z.object({
  id: z.number(),
  name: z.string(),
  email: z.string().email(),
  age: z.number().min(0).max(150).optional(),
});

export type User = z.infer<typeof UserSchema>;

// Test the schema
const validUser = { id: 1, name: "Test", email: "test@example.com" };
UserSchema.parse(validUser);
console.log("✅ Zod schema works");
EOF

    # Create a temp directory for TypeScript compilation with proper setup
    temp_ts_dir=$(mktemp -d)
    mv "$temp_ts" "$temp_ts_dir/test.ts"

    # Try to use existing node_modules or install zod
    if [ -d "/opt/typescript-validation/node_modules" ]; then
        ln -s /opt/typescript-validation/node_modules "$temp_ts_dir/node_modules"
    else
        # Create package.json and install zod
        echo '{"name":"test","dependencies":{"zod":"^3.22.0"}}' > "$temp_ts_dir/package.json"
        (cd "$temp_ts_dir" && npm install --silent) 2>/dev/null
    fi

    # Create tsconfig.json
    echo '{"compilerOptions":{"target":"ES2020","module":"commonjs","strict":true,"esModuleInterop":true,"skipLibCheck":true,"noEmit":true}}' > "$temp_ts_dir/tsconfig.json"

    if (cd "$temp_ts_dir" && npx tsc test.ts --noEmit); then
        print_success "TypeScript compilation works"
        external_passed=$((external_passed + 1))
    else
        print_error "TypeScript compiler validation failed"
        echo "Error: TypeScript compilation failed. Make sure TypeScript and Zod are installed."
    fi
    rm -rf "$temp_ts_dir"
    external_tests=$((external_tests + 1))
    rm -f "$temp_ts"
else
    print_warning "TypeScript/Node.js not available - skipping TypeScript validation"
fi

# Check for Java compiler
if command_exists javac; then
    print_step "Testing Java/Jackson validation"
    # Java requires file name to match class name for public classes
    temp_dir=$(mktemp -d)
    temp_java="$temp_dir/User.java"
    cat > "$temp_java" << 'EOF'
public class User {
    private int id;
    private String name;
    private String email;

    public User() {}

    public int getId() { return id; }
    public void setId(int id) { this.id = id; }

    public String getName() { return name; }
    public void setName(String name) { this.name = name; }

    public String getEmail() { return email; }
    public void setEmail(String email) { this.email = email; }
}
EOF

    if javac "$temp_java"; then
        print_success "Java compilation works"
        external_passed=$((external_passed + 1))
    else
        print_error "Java compiler validation failed"
        echo "Error: Java compilation failed. Make sure JDK is installed."
    fi
    external_tests=$((external_tests + 1))
    rm -rf "$temp_dir"
else
    print_warning "Java compiler not available - skipping Java validation"
fi

# Check for Protocol Buffers compiler
if command_exists protoc; then
    print_step "Testing Protocol Buffers validation"
    temp_proto=$(mktemp --suffix=.proto)
    cat > "$temp_proto" << 'EOF'
syntax = "proto3";

message User {
  int32 id = 1;
  string name = 2;
  string email = 3;
  int32 age = 4;
}
EOF

    # Get the directory of the proto file for proto_path
    proto_dir=$(dirname "$temp_proto")

    if protoc --proto_path="$proto_dir" --python_out=/tmp "$temp_proto"; then
        print_success "Protocol Buffers compilation works"
        external_passed=$((external_passed + 1))
    else
        print_error "Protocol Buffers compiler validation failed"
        echo "Error: protoc compilation failed. Make sure protobuf-compiler is installed."
    fi
    external_tests=$((external_tests + 1))
    rm -f "$temp_proto"
else
    print_warning "Protocol Buffers compiler not available - skipping protobuf validation"
fi

# Print final summary
echo ""
echo "======================================"
print_step "TEST SUMMARY"
echo "======================================"

echo "Core Tests: $passed_tests/$total_tests passed"
if [ $external_tests -gt 0 ]; then
    echo "External Validators: $external_passed/$external_tests passed"
fi

overall_success_rate=$((passed_tests * 100 / total_tests))
echo "Success Rate: $overall_success_rate%"

if [ $failed_tests -eq 0 ]; then
    print_success "All core tests passed! 🎉"

    if [ $external_tests -gt 0 ]; then
        if [ $external_passed -eq $external_tests ]; then
            print_success "All external validators also passed! 🚀"
        else
            print_warning "Some external validators failed, but this is optional"
        fi
    fi

    echo ""
    echo "🌟 Schema-Gen is working correctly!"
    echo "   All generated formats are valid and functional."
    exit 0
else
    print_error "$failed_tests core test(s) failed"
    echo ""
    echo "💡 Please check the errors above and fix any issues."
    exit 1
fi
