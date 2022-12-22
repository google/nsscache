FROM python:3.10
RUN apt-get update
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get install -y libsasl2-dev libldap2-dev libssl-dev slapd ldap-utils

ENV VIRTUAL_ENV=/opt/venv
RUN python -m venv $VIRTUAL_ENV
ENV PATH=$VIRTUAL_ENV/bin:$PATH

WORKDIR /code

ADD ./requirements.txt /code/requirements.txt
RUN pip install -r requirements.txt

ADD . /code
RUN python setup.py test
RUN python setup.py install
RUN tests/slapd-regtest
