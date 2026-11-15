#!/bin/bash
# Pod start: install the SSH key passed by render-remote.sh (env PUBLIC_KEY), start sshd, mark ready.
mkdir -p /root/.ssh /run/sshd /root/job
echo "$PUBLIC_KEY" > /root/.ssh/authorized_keys
chmod 700 /root/.ssh && chmod 600 /root/.ssh/authorized_keys
/usr/sbin/sshd
touch /root/ready
exec sleep infinity
