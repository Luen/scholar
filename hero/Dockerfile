FROM ulixee/ulixee-cloud:latest

# Use su to switch to ulixee (available in base; no apt needed)
# su-exec is from s6-overlay if present; otherwise use su
COPY hero-entrypoint.sh /hero-entrypoint.sh
RUN chmod +x /hero-entrypoint.sh

ENTRYPOINT ["/hero-entrypoint.sh"]
CMD ["xvfb-run", "npx", "@ulixee/cloud", "start", "--port=1818"]
