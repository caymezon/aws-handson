#!/bin/bash
set -e

echo "=== Stopping Tomcat ==="
systemctl stop tomcat || true

# 古い WAR とデプロイ済みディレクトリを削除
rm -f  /opt/tomcat/current/webapps/ROOT.war
rm -rf /opt/tomcat/current/webapps/ROOT
rm -f  /opt/tomcat/current/webapps/webapp.war

echo "=== Tomcat stopped and old webapp removed ==="
