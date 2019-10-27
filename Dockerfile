FROM alpine:3.10.3

LABEL maintainer="Toni Kaplan"
LABEL repository="https://github.com/tonikaplan-pear/create-pull-request"
LABEL homepage="https://github.com/tonikaplan-pear/create-pull-request"

LABEL com.github.actions.name="Create Pull Request"
LABEL com.github.actions.description="Creates a pull request for changes to your repository in the actions workspace"
LABEL com.github.actions.icon="git-pull-request"
LABEL com.github.actions.color="gray-dark"

COPY LICENSE README.md /

RUN apk add python3-dev git git-lfs

COPY requirements.txt /tmp/
RUN pip3 install --requirement /tmp/requirements.txt

COPY create-pull-request.py /create-pull-request.py
ENTRYPOINT [ "/create-pull-request.py" ]
