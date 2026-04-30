#!/bin/bash
set -e
/opt/tomcat/bin/shutdown.sh 2>/dev/null || true
sleep 5
pkill -f 'org.apache.catalina.startup.Bootstrap' 2>/dev/null || true
exit 0
