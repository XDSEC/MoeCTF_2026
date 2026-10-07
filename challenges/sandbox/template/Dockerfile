FROM library/python:3.12-alpine

USER 0
# COPY ./lazybox /bin/busybox
COPY --chown=0:0 ./main.py /usr/lib/challenge/main.py
COPY --chown=0:0 ./wrapper.sh /usr/lib/challenge/wrapper.sh
RUN chmod 500 /usr/lib/challenge/main.py
RUN chmod 500 /usr/lib/challenge/wrapper.sh

EXPOSE 9999

CMD ["/usr/lib/challenge/wrapper.sh"]