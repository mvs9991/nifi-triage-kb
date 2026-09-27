def sql = "UPDATE file_audit SET status = 'LOADED' WHERE file_name = ?"
def target = "s3://acme-orders-curated/audit/"
