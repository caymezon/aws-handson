#!/bin/bash
set -e

REGION="ap-northeast-1"
EMPLOYEE_ID=$(cat /etc/employee_id)

echo "=== Fetching DB credentials from SSM Parameter Store ==="
DB_HOST=$(aws ssm get-parameter \
  --name "/${EMPLOYEE_ID}/cpapp/db-host" \
  --region "$REGION" \
  --query Parameter.Value \
  --output text)

DB_PASSWORD=$(aws ssm get-parameter \
  --name "/${EMPLOYEE_ID}/cpapp/db-password" \
  --region "$REGION" \
  --query Parameter.Value \
  --output text)

echo "=== Configuring Tomcat environment ==="
cat > /opt/tomcat/current/bin/setenv.sh << EOF
export DB_HOST=${DB_HOST}
export DB_PASSWORD=${DB_PASSWORD}
EOF
chmod +x /opt/tomcat/current/bin/setenv.sh
chown tomcat:tomcat /opt/tomcat/current/bin/setenv.sh

# WAR 繧・ROOT.war 縺ｫ繝ｪ繝阪・繝・医さ繝ｳ繝・く繧ｹ繝医ヱ繧ｹ縺ｪ縺励〒繧｢繧ｯ繧ｻ繧ｹ縺ｧ縺阪ｋ繧医≧縺ｫ縺吶ｋ・・mv /opt/tomcat/current/webapps/webapp.war /opt/tomcat/current/webapps/ROOT.war
chown tomcat:tomcat /opt/tomcat/current/webapps/ROOT.war

echo "=== Starting Tomcat ==="
systemctl start tomcat

echo "=== Tomcat started ==="

