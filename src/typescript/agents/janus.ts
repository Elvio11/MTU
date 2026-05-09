import { AgentMessageEnvelope } from "../shared/envelope";
import { Keypair } from "@solana/web3.js";

export class JanusAgent {
  public keypair: Keypair | null = null;
  
  constructor() {
    console.log("JanusAgent initialized");
  }

  async checkSniperBalance(): Promise<number> {
    return 1.5;
  }
}
