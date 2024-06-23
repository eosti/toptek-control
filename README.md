# Toptek Control
A repo housing the code for controlling a Toptek PA70 power amplifier. 
Most of this repo won't make sense unless you have the specific hardware setup that I need to document still, so like, that'll come eventually. 
If you're in desperate need of a solution to control a Toptek PA70: first off, why, second off, shoot me an email to light the fire under my butt to document it properly. 
But again, why???

## Installing
The Arduino code is a PlatformIO project, and the python library is managed by Poetry. 

## Contributing
Issues and PRs are always welcome! 
If contributing code, please first run the linting + style suite as follows: `isort . && black . && flake8 . && mypy .` for Python code or use `clang-format` for Arduino stuff.
