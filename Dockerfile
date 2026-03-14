FROM python:3.9
COPY . /home
WORKDIR /home
RUN pip3 install -r requirements.txt
ENV PYTHONPATH="."
CMD ["python", "run_loop.py"]
