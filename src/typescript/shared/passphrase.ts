import * as readline from 'readline';

export const readPassphraseStdin = (prompt: string = 'Enter Sniper passphrase: '): Promise<string> => {
  return new Promise((resolve, reject) => {
    const rl = readline.createInterface({
      input: process.stdin,
      output: process.stdout,
    });
    
    // Hide input (Windows/Linux/Mac)
    if (process.stdin.isTTY) {
      process.stdin.setRawMode(true);
    }
    
    process.stdout.write(prompt);
    
    let passphrase = '';
    process.stdin.on('data', (char: Buffer) => {
      const byte = char[0];
      
      // Enter key
      if (byte === 0x0d || byte === 0x0a) {
        process.stdout.write('\n');
        if (process.stdin.isTTY) {
          process.stdin.setRawMode(false);
        }
        rl.close();
        resolve(passphrase);
        return;
      }
      
      // Backspace
      if (byte === 0x7f || byte === 0x08) {
        if (passphrase.length > 0) {
          passphrase = passphrase.slice(0, -1);
          process.stdout.write('\b \b');
        }
        return;
      }
      
      // Printable characters
      if (byte >= 0x20 && byte <= 0x7e) {
        passphrase += String.fromCharCode(byte);
        process.stdout.write('*');
      }
    });
    
    process.stdin.on('error', (err: Error) => {
      reject(err);
    });
  });
};
