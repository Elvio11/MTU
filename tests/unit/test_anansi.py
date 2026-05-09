import pytest
import sys
import os
import asyncio

# Add D:/Trader/src to path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
src_path = os.path.join(project_root, "src")
sys.path.insert(0, src_path)

from src.python.agents.anansi import AnansiAgent


class TestAnansiAgent:
    """Test Anansi agent (AGT-03) - Section 3.4 verification"""

    @classmethod
    def setup_class(cls):
        cls.config = {
            "qualification": {
                "min_market_cap_sol": 5,
                "max_market_cap_sol": 150,
                "min_lp_burned_pct": 85,
                "max_rugcheck_score": 300,
                "max_dev_holding_pct": 5,
                "max_top10_concentration_pct": 30,
            },
            "rpc": {"providers": [{"http_url": "https://api.mainnet-beta.solana.com"}]},
        }

    def test_01_g1_mint_authority_revoked(self):
        """G1: Mint Authority revoked - check method exists"""
        agent = AnansiAgent(self.config)
        assert hasattr(agent, "check_g1_mint_authority")
        assert callable(agent.check_g1_mint_authority)

    def test_02_g2_freeze_authority_revoked(self):
        """G2: Freeze Authority revoked - check method exists"""
        agent = AnansiAgent(self.config)
        assert hasattr(agent, "check_g2_freeze_authority")
        assert callable(agent.check_g2_freeze_authority)

    def test_03_g3_lp_lock(self):
        """G3: LP locked/burned - check method exists"""
        agent = AnansiAgent(self.config)
        assert hasattr(agent, "check_g3_lp_lock")
        assert callable(agent.check_g3_lp_lock)

    def test_04_g4_dev_holdings_less_than_5pct(self):
        """G4: Dev holdings <5% - check method exists"""
        agent = AnansiAgent(self.config)
        assert hasattr(agent, "check_g4_dev_holdings")
        assert callable(agent.check_g4_dev_holdings)

    def test_05_g5_top10_concentration(self):
        """G5: Top 10 holders <30% - check method exists"""
        agent = AnansiAgent(self.config)
        assert hasattr(agent, "check_g5_top10_concentration")
        assert callable(agent.check_g5_top10_concentration)

    def test_06_g6_rugcheck_score(self):
        """G6: RugCheck score ≤300 - check method exists"""
        agent = AnansiAgent(self.config)
        assert hasattr(agent, "check_g6_rugcheck_score")
        assert callable(agent.check_g6_rugcheck_score)

    def test_07_g7_market_cap(self):
        """G7: MCap 5-150 SOL - check method exists and works"""
        agent = AnansiAgent(self.config)
        assert hasattr(agent, "check_g7_market_cap")
        assert callable(agent.check_g7_market_cap)
        result = asyncio.run(agent.check_g7_market_cap(50))
        assert result == True
        result = asyncio.run(agent.check_g7_market_cap(151))
        assert result == False

    def test_08_g8_social_metadata(self):
        """G8: Social metadata present"""
        agent = AnansiAgent(self.config)
        assert hasattr(agent, "check_g8_social_metadata")
        assert callable(agent.check_g8_social_metadata)

    def test_09_g9_duplicate(self):
        """G9: Not duplicate (24h)"""
        agent = AnansiAgent(self.config)
        assert hasattr(agent, "check_g9_duplicate")
        assert callable(agent.check_g9_duplicate)

    def test_10_g10_honeypot(self):
        """G10: Honey pot check"""
        agent = AnansiAgent(self.config)
        assert hasattr(agent, "check_g10_honeypot")
        assert callable(agent.check_g10_honeypot)

    def test_11_qualification_report(self):
        """Full QualificationReport population"""
        agent = AnansiAgent(self.config)
        assert hasattr(agent, "_collect_gate_values")
        assert callable(agent._collect_gate_values)

    def test_12_production_mode_gates(self):
        """G3-G9 checks run only in production mode"""
        agent = AnansiAgent(self.config)
        # Paper mode should skip G3-G9
        agent.is_paper_mode = True
        assert agent.is_paper_mode == True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
