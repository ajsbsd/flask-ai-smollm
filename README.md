Running a Self-Contained LLM for Less Than $10 a Month
=======================================================

1. OPERATING SYSTEM
-------------------
This guide uses Ubuntu for the initial walkthrough. It has also been tested
and confirmed working on Debian 13 and OpenBSD 7.9-current.

Install the following packages via apt:

    sudo apt install build-essential git git-lfs python3-venv


2. PYTHON VIRTUAL ENVIRONMENT
------------------------------
The goal is a single, self-contained Python virtual environment. All
dependencies will be installed inside it so nothing touches your system Python.

    python3 -m venv venv
    source venv/bin/activate


3. CLONE THE REPOSITORY
------------------------
    git clone https://github.com/ajsbsd/flask-ai-smollm
    cd flask-ai-smollm


4. DOWNLOAD THE MODEL
----------------------
This project uses SmolLM2 135M Instruct, a quantized model small enough to
run without AVX extensions on hardware destined for the scrap pile.

Download the GGUF from HuggingFace:

    https://huggingface.co/HuggingFaceTB/SmolLM2-135M-Instruct-GGUF

File: SmolLM2-135M-Instruct-Q4_K_S.gguf

Place it in the models directory and rename it to current.gguf:

    mkdir -p models
    cp SmolLM2-135M-Instruct-Q4_K_S.gguf models/current.gguf


5. BUILD llama-cpp-python
--------------------------
llama-cpp-python must be compiled from source to match your hardware. A
build script is provided:

    bash build.sh

The script sets the required CMAKE flags for your platform. If you need to
customize the build (e.g. CUDA, Metal, AVX toggles), edit build.sh before
running.


6. INSTALL PYTHON REQUIREMENTS
--------------------------------
    pip install -r requirements.txt

Note: requirements.txt is still evolving as testing continues across
platforms. If you hit a missing dependency, open an issue on the repository.


7. RUNTIME
-----------
By default the application binds to 127.0.0.1:3000.

Start the server:

    bash run.sh

To expose it remotely you have two options:

  a) SSH tunnel (recommended for quick access or testing)
     From your local machine:

         ssh -L 3000:127.0.0.1:3000 user@your-server

  b) nginx reverse proxy
     Configure nginx to proxy requests to 127.0.0.1:3000. Full nginx
     configuration is beyond the scope of this document.

Once you can reach the gunicorn service, open the terminal interface in your
browser and run the AI test command:

    ai print some hello, worlds


8. VERIFICATION
----------------
A successful response confirms:

  - SmolLM2-135M-Instruct-Q4_K_S.gguf loaded correctly from ./models/
  - llama-cpp-python compiled and linked properly
  - The Flask/gunicorn stack is routing requests to the model
  - Inference is producing output

If you see an error, check:

  - That models/current.gguf exists and is a text-generation GGUF
  - That the virtual environment is active when running run.sh
  - The gunicorn log output for any load-time exceptions
