from torchvision import transforms, datasets
from torch.utils.data import DataLoader, random_split


def get_dataloaders(
    data_path: str, batch_size: int
) -> tuple[DataLoader, DataLoader, DataLoader]:
    normalize_tensor = transforms.Compose(
        [
            transforms.ToTensor(),
            transforms.Normalize(
                mean=[0.4914, 0.4822, 0.4465], std=[0.2023, 0.1994, 0.2010]
            ),  # normalize the cifar10 images
        ]
    )

    train_dataset = datasets.CIFAR10(
        root=data_path, train=True, download=True, transform=normalize_tensor
    )
    train_dataset, validate_dataset = random_split(train_dataset, [0.8, 0.2])
    test_dataset = datasets.CIFAR10(
        root=data_path, train=False, download=True, transform=normalize_tensor
    )

    train_loader = DataLoader(
        train_dataset,
        batch_size=batch_size,
        shuffle=True,
    )
    validation_loader = DataLoader(
        validate_dataset,
        batch_size=batch_size,
        shuffle=False,
    )
    test_loader = DataLoader(
        test_dataset,
        batch_size=batch_size,
        shuffle=False,
    )

    return train_loader, validation_loader, test_loader
