# =============================================================
# Stage 1: Maven で Spring Boot WAR をビルド
# =============================================================
FROM public.ecr.aws/docker/library/maven:3.9-amazoncorretto-17 AS builder
WORKDIR /build
COPY app/pom.xml .
COPY app/src ./src
RUN mvn package -DskipTests

# =============================================================
# Stage 2: Tomcat コンテナに WAR を配置
# =============================================================
FROM public.ecr.aws/docker/library/tomcat:10.1-jdk17-corretto

# デフォルトの ROOT アプリを削除して Spring Boot WAR を ROOT として配置
# → http://<ALB>/ で直接アクセスできる（コンテキストパスなし）
RUN rm -rf /usr/local/tomcat/webapps/*
COPY --from=builder /build/target/webapp.war /usr/local/tomcat/webapps/ROOT.war

EXPOSE 8080
