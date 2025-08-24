#!/bin/bash
# Nancy Brain Environment Setup Script
# This script activates the roman-slack-bot conda environment

echo "🚀 Activating Nancy Brain environment..."

# Fix OpenMP issue common in conda environments
export KMP_DUPLICATE_LIB_OK=TRUE

# Check if conda is available
if ! command -v conda &> /dev/null; then
    echo "❌ Conda not found. Please install Anaconda/Miniconda first."
    exit 1
fi

# Check if the environment exists
if ! conda env list | grep -q "roman-slack-bot"; then
    echo "❌ Environment 'roman-slack-bot' not found."
    echo "💡 Available environments:"
    conda env list
    exit 1
fi

# Activate the environment
conda activate roman-slack-bot

echo "✅ Nancy Brain environment activated!"
echo "🔍 Python version: $(python --version)"
echo "📦 Key packages:"
python -c "
try:
    import txtai, fastapi, pydantic
    print(f'   - txtai: {txtai.__version__}')
    print(f'   - fastapi: {fastapi.__version__}')
    print(f'   - pydantic: {pydantic.__version__}')
    print('✅ All packages ready!')
except ImportError as e:
    print(f'❌ Missing package: {e}')
"

echo ""
echo "🎯 You can now run:"
echo "   - python scripts/build_knowledge_base.py --help"
echo "   - python scripts/manage_articles.py --help" 
echo "   - python connectors/http_api/app.py"
echo "   - pytest tests/"
