
if [[ ! $(which pep8) ]]; then
  do_progress_quiet "Installing Python 'pep8' for tests" \
    pip install pep8
fi

if [[ ! $(which coverage) ]]; then
  do_progress_quiet "Installing Python 'coverage' for tests" \
    pip install coverage
fi
