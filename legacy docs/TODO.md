  ## some explanations below
1. Deployment works, but runtime is not
2. Shared hostings disallow symbolic links and private pip installation
   so, we need to do it manually (this ge-pip thing)
3. We should be mandatory python 3.6
4. We have problem with psycopg2-binary and psycopg2 at all - it is native drive
  that have system dependent parts. This will not work on shared hosting - use psycopg (pure python implementation) 

To debug all this you need aceess to ssh. To organize it do the following:
1. If you already have public and private keys (for example if you using git with gitxxx urls and not https://) take your public key and put it in cpanel
2. Othervise: run `ssh-keygen -t rsa` without any other params, then go to folder .ssh in your home directory, take public key (id_rsa.pub) from there and add to cpanel
3. Then you will be able to run `ssh rcsjkudmfy@server704.shared.spaceship.host -p 21098` and enter hosting shell. There you `cd myflaskapp` and run everething manually 
to see if thing are working  