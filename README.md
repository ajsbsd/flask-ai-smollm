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


4. DOWNLOAD A TEXT GENERATION MODEL (GGUF)
-------------------------------------------
Place your model file inside the ./models directory.

For initial testing we recommend the HuggingFace SmolLM 135M model. It is
small enough to run without AVX extensions on hardware that would otherwise
be destined for the scrap pile -- a good first proof-of-concept before
committing to larger models.

Download the GGUF from HuggingFace and place it in:

    ./models/


5. BUILD llama-cpp-python
--------------------------
llama-cpp-python must be compiled from source to match your hardware. A
build script is provided:

    bash build.sh

The script sets the required CMAKE flags for your platform. If you need to
customize the build (e.g. CUDA, Metal, AVX toggles), edit build.sh before
running.

    # Placeholder -- exact CMAKE flags will be documented here once finalized.
    # Example structure:
    # CMAKE_ARGS="-DLLAMA_BLAS=ON -DLLAMA_BLAS_VENDOR=OpenBLAS" \
    #   pip install llama-cpp-python --no-binary llama-cpp-python


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

     A managed tunnel service can simplify this if you do not control the
     network between your client and server.

  b) nginx reverse proxy
     Configure nginx to proxy requests to 127.0.0.1:3000. Full nginx
     configuration is beyond the scope of this document.

Once you can reach the gunicorn service (either via tunnel or proxy), open
the terminal interface in your browser and run the AI test command:

    ai print some hello, worlds


8. VERIFICATION
----------------
A successful response to the command above confirms:

  - The GGUF model loaded correctly from ./models/
  - llama-cpp-python compiled and linked properly
  - The Flask/gunicorn stack is routing requests to the LLM
  - Inference is producing output

If you see an error at this step, check:

  - That the model file exists in ./models/ and is a text-generation GGUF
    (not an image diffusion model such as FLUX)
  - That the virtual environment is active when running run.sh
  - The gunicorn log output for any load-time exceptions
