import hydra
import torch
import torch.nn.utils.prune as prune
from torch import nn
from pathlib import Path
from omegaconf import DictConfig, OmegaConf
from architecture.dataloaders import get_dataloaders
from architecture.construct_model import construct_model
from architecture.pruning_loop import prune_model
import architecture.utility as utility
import datetime
import wandb
import logging
import pandas as pd

logger = logging.getLogger(__name__)


@hydra.main(config_path="conf", config_name="config", version_base="1.2")
def main(cfg: DictConfig) -> None:
    """Main function for the pruning entry point

    Args:
        cfg (DictConfig): Hydra config object with all the settings. (Located in conf/config.yaml)
    """

    logger.info(OmegaConf.to_yaml(cfg))

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    # Save the model to the Hydra output directory
    hydra_output_dir = Path(
        hydra.core.hydra_config.HydraConfig.get().runtime.output_dir
    )
    current_date = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    logger.info(f"Hydra output directory: {hydra_output_dir}")

    if cfg.seed.is_set:
        utility.training.set_reproducibility(cfg.seed.value)

    base_model: nn.Module = construct_model(cfg).to(device)
    train_dl, valid_dl, test_dl = get_dataloaders(cfg)
    cross_entropy = nn.CrossEntropyLoss()
    base_test_loss, base_test_accuracy, base_test_top5acc = utility.training.test(
        module=base_model,
        test_dl=test_dl,
        loss_function=cross_entropy,
        device=device,
    )
    logger.info(f"Base test loss: {base_test_loss:.4f}")
    logger.info(f"Base test accuracy: {base_test_accuracy:.2f}%")
    logger.info(f"Base test top5 accuracy: {base_test_top5acc:.2f}%")

    results_csv = hydra_output_dir / f"{current_date}.csv"
    utility.training.create_output_csv(
        results_csv,
        [
            "Model",
            "Dataset",
            "Total pruning percentage",
            "Finetune epochs",
            "Test loss",
            "Test accuracy",
            "Test top-5 accuracy",
            "Difference to baseline",
        ],
    )

    results = []
    for i in range(cfg.repeat):
        logger.info(f"Repeat {i+1}/{cfg.repeat}")

        model = construct_model(cfg).to(device)
        optimizer = torch.optim.AdamW(
            model.parameters(),
            lr=cfg.optimizer.lr,
            weight_decay=cfg.optimizer.weight_decay,
        )
        pruning_parameters = utility.pruning.get_parameters_to_prune(
            model, (nn.Linear, nn.Conv2d, nn.BatchNorm2d)
        )
        pruning_amount = int(
            round(
                utility.pruning.calculate_parameters_amount(pruning_parameters)
                * cfg.pruning.iteration_rate
            )
        )

        wandb_run = None
        if cfg.wandb.logging:
            wandb_run = wandb.init(project=cfg.wandb.project)

        prune_model(
            model=model,
            method=prune.L1Unstructured,
            parameters_to_prune=pruning_parameters,
            optimizer=optimizer,
            loss_fn=cross_entropy,
            iterations=cfg.pruning.iterations,
            finetune_epochs=cfg.pruning.finetune_epochs,
            pruning_amount=pruning_amount,
            train_dl=train_dl,
            valid_dl=valid_dl,
            device=device,
            wandb_run=wandb_run,
        )

        test_loss, test_accuracy, test_top5acc = utility.training.test(
            module=model,
            test_dl=test_dl,
            loss_function=cross_entropy,
            device=device,
        )
        logger.info(f"Test loss: {test_loss:.4f}")
        logger.info(f"Test accuracy: {test_accuracy:.2f}%")
        logger.info(f"Test top5 accuracy: {test_top5acc:.2f}%")

        results.append(
            {
                "Model": cfg.model.name,
                "Dataset": cfg.dataset.name,
                "Total pruning percentage": cfg.pruning.iterations
                * cfg.pruning.iteration_rate,
                "Finetune epochs": cfg.pruning.finetune_epochs,
                "Test loss": test_loss,
                "Test accuracy": test_accuracy,
                "Test top-5 accuracy": test_top5acc,
                "Difference to baseline": base_test_accuracy - test_accuracy,
            }
        )

        if cfg.save_checkpoints:
            current_date = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            torch.save(
                model.state_dict(),
                hydra_output_dir / f"{cfg.model.name}_{i}_{current_date}.pth",
            )

    results_df = pd.DataFrame(results)
    results_df.round(2)
    accuracy_mean = results_df["Test accuracy"].mean()
    accuracy_std = results_df["Test accuracy"].std()
    top5_accuracy_mean = results_df["Test top-5 accuracy"].mean()
    top5_accuracy_std = results_df["Test top-5 accuracy"].std()
    difference_mean = results_df["Difference to baseline"].mean()
    difference_std = results_df["Difference to baseline"].std()
    logger.info(f"Mean accuracy {accuracy_mean:.2f}% ± {accuracy_std:.2f}%")
    logger.info(
        f"Mean difference to baseline {difference_mean:.2f}% ± {difference_std:.2f}%"
    )
    logger.info(
        f"Mean top-5 accuracy {top5_accuracy_mean:.2f}% ± {top5_accuracy_std:.2f}%"
    )
    results_df.to_csv(
        results_csv, mode="a", header=False, index=False, float_format="%.2f"
    )


if __name__ == "__main__":
    main()
