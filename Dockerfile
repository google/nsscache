FROM python:3.7
RUN apt-get update
RUN apt-get install -y libnss-db libsasl2-dev libldap2-dev libssl-dev
RUN mkdir /code
WORKDIR /code
ADD requirements.txt /code/
RUN pip install -r requirements.txt
ADD . /code/

CMD [ "./runtests.py" ]
