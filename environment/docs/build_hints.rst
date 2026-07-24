from /app:
  mvn -q -DskipTests package -Dhz.marker=/app/environment/k1
  java -jar /app/drive/target/drive-1.0.0-shaded.jar
output:
  /app/output/hardened_policy_pack.json
